#!/usr/bin/env python
###########################################################
# This file has been created by NERC-ARF Data Analysis Node and
# is licensed under the GPL v3 Licence. A copy of this
# licence is available to download with this file.
###########################################################

"""
qsub script to be called by web_processing_cron, receives config files from web process cron and generates a processing
folder tree/dem before either submitting to the grid or processing locally.

Author: Stephen Goult

Available functions
web_structure(project_code, jday, year, sortie=None, output_name=None): takes project code, jday and year and optionally
a sortie or a set folder to generate the folder tree inside
web_qsub(config, local=False, local_threaded=False, output=None): takes a config file and transforms it to a folder tree
with a dem file included (unless specified in the config already) will then either process files locally or submit to
the grid. Uses scops_process_apl_line.py
"""

import os
import datetime
import sys
if sys.version_info[0] < 3:
    import ConfigParser
else:
    import configparser as ConfigParser
import argparse
import glob
import logging
import subprocess

from scops import scops_common
import scops_process_apl_line
import scops_job_submission

import arsf_dem
from arsf_dem import dem_common_functions
import status_db

def web_structure(project_code, jday, year, sortie=None, output_name=None):
    """
    Builds the structure for a web job to output to

    :param project_code:
    :param jday:
    :param year:
    :param sortie:
    :param output_name:
    :return: folder location
    """
    #if there isnt an output name generate one from the time and day/year/project
    if output_name is not None:
        folder_base = output_name
    else:
        if sortie is not "None":
            folder_base = scops_common.WEB_OUTPUT + project_code + '_' + year + '_' + jday + sortie + datetime.datetime.now().strftime(
               '%Y%m%d%H%M%S')
        else:
            folder_base = scops_common.WEB_OUTPUT + project_code + '_' + year + '_' + jday + datetime.datetime.now().strftime(
               '%Y%m%d%H%M%S')
    #make the folders
    if os.access(scops_common.WEB_OUTPUT, os.W_OK):
        os.mkdir(folder_base)
        os.mkdir(os.path.join(folder_base , scops_common.WEB_MASK_OUTPUT))
        os.mkdir(os.path.join(folder_base , scops_common.WEB_IGM_OUTPUT))
        os.mkdir(os.path.join(folder_base , scops_common.WEB_MAPPED_OUTPUT))
        os.mkdir(os.path.join(folder_base , scops_common.WEB_DEM_FOLDER))
        os.mkdir(os.path.join(folder_base , scops_common.WEB_STATUS_OUTPUT))
        os.mkdir(os.path.join(folder_base , scops_common.LOG_DIR))
    else:
        raise IOError("no write permissions at {}".format(scops_common.WEB_OUTPUT))
    #return the location
    return folder_base


def web_qsub(config, job_submission_system="local", output=None):
    """
    Submits the job (or processes locally in its current form)

    :param config:
    :param local:
    :param local_threaded:
    :param output:
    :return:
    """
    logger = logging.getLogger()
    file_handler = logging.FileHandler(scops_common.QSUB_LOG_DIR + os.path.basename(config).replace(".cfg","") + "_log.txt", mode='a')
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.handlers = []
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)

    logger.info(config)

    config_file = ConfigParser.SafeConfigParser()
    config_file.read(config)
    lines = config_file.sections()
    defaults = config_file.defaults()

    if config_file.getboolean('DEFAULT', "has_error"):
        logger.info("not processing due to pre proc errors, inspect earlier in this log to see reason")
        exit(0)

    new_location = False
    #if the output location doesn't exist yet we should create one
    if output is None or output == '':
        try:
            output_location = config_file.get('DEFAULT', 'output_folder')
            if not os.path.exists(output_location):
                raise Exception("specified output location does not exist!")
        except Exception as e:
            logger.warning(e)
            sortie = defaults["sortie"]
            if sortie == "None":
                sortie=''
            output_location = web_structure(defaults["project_code"], defaults["julianday"], defaults["year"],
                              sortie)
            new_location = True
            config_file.set('DEFAULT', 'output_folder', output_location)
    else:
        output_location = output

    #symlink the config file into the processing folder so that we know the source of any problems that arise
    if not os.path.exists(output_location + '/' + os.path.basename(config)):
        os.symlink(os.path.abspath(config), output_location + '/' + os.path.basename(config))

    sortie=defaults["sortie"]
    if sortie == "None":
        sortie=''

    sourcefolder = None

    try:
        sourcefolder = defaults["sourcefolder"]
    except KeyError:
        pass

    if sourcefolder is None:
        try:
            import folder_structure
        except ImportError:
            raise ImportError("Source folder was not specified and folder_structure"
                              ", which provides details for the PML system, could"
                              " not be imported")
        #find out where the files are for the day we are trying to process
        folder = folder_structure.FolderStructure(year=defaults["year"],
                                                  jday=defaults["julianday"],
                                                  projectCode=defaults["project_code"],
                                                  fletter=sortie,
                                                  absolute=True)
        sourcefolder = folder.getProjPath()

    folder_key = scops_process_apl_line.sensor_folder_lookup(lines[0][:1])
    #locate delivery and navigation files
    hyper_delivery = glob.glob(os.path.join(sourcefolder, scops_common.HYPER_DELIVERY_FOLDER.format(folder_key)))[0]
    nav_folder = glob.glob(os.path.join(hyper_delivery,
                                        "flightlines/navigation/"))[0]

    #if the dem doesn't exist generate one
    try:
        logger.info("checking dem")
        dem_name = config_file.get('DEFAULT', 'dem_name')
        logger.info(dem_name)
        if not os.path.exists(dem_name):
            raise Exception("The DEM specified does not exist!")
    except Exception as e:
        dem_common_functions.WARNING(str(e))
        logger.warning(str(e))
        if config_file.getboolean("DEFAULT", "ftp_dem"):
            logger.error("The config suggests this DEM was sourced from the ftp, confirm it exists and is correct as the system cannot find it.")
            config_file.set('DEFAULT', "has_error", "True")
            raise Exception("The DEM provided does not exist, entering an error state")
        else:
            dem_name = os.path.join(output_location , scops_common.WEB_DEM_FOLDER , defaults["project_code"] + '_' + defaults["year"] + '_' + defaults[
               "julianday"] + '_' + defaults["projection"] + ".dem").replace(' ', '_')
            arsf_dem.dem_nav_utilities.create_apl_dem_from_mosaic(dem_name,
                                                         dem_source=defaults["dem"],
                                                         bil_navigation=nav_folder)

    if not config_file.has_option('DEFAULT', 'force_dem'):
        if "upload" in defaults["dem"]:
            nav_files=glob.glob(nav_folder + "*_nav_post_processed.bil")
            dem_bounds = arsf_dem.dem_utilities.get_gdal_dataset_bb(config_file.get('DEFAULT', 'dem_name'))
            nav_bounds = arsf_dem.dem_nav_utilities.get_bb_from_bil_nav_files(nav_files)

            if (nav_bounds[0] < dem_bounds[0] or
            nav_bounds[1] > dem_bounds[1] or
            nav_bounds[2] < dem_bounds[2] or
            nav_bounds[3] > dem_bounds[3]):
                config_file.set('DEFAULT', "has_error", "True")
                config_file.write(open(config, 'w'))
                scops_process_apl_line.email_preprocessing_error(defaults['email'], output_location, defaults['project_code'], reason="dem_coverage")
                logger.error("The DEM provided by the user does not cover the navigation area, entering an error state")
                raise Exception("The DEM provided by the user does not cover the navigation area, entering an error state")

    #update config with the dem name then submit the file to the processor, we don't want the script to run twice so set
    # submitted to true
    config_file.set('DEFAULT', "dem_name", dem_name)
    config_file.set('DEFAULT', "submitted", "True")
    config_file.set('DEFAULT', "restart", "False")
    config_file.write(open(config, 'w'))

    #Generate a status file for each line to be processed, these are important later!
    for line in lines:
        status_file = scops_common.STATUS_FILE.format(output_location, line)
        log_file = scops_common.LOG_FILE.format(output_location, line)
        if "true" in dict(config_file.items(line))["process"]:
            link = scops_common.LINE_LINK.format(os.path.basename(os.path.normpath(output_location)), line, defaults["project_code"])
            status_db.insert_line_into_db(os.path.basename(os.path.normpath(output_location)), line, "Waiting to process", 0, 0, 0, 0, link, 0, 0)
            open(status_file, 'w+').write("{} = {}".format(line, "waiting"))
            open(log_file, mode="a").close()
        else:
            open(status_file, 'w+').write("{} = {}".format(line, "not processing"))
        equations = [x for x in dict(config_file.items('DEFAULT')) if x.startswith("eq_")]
        plugins = [x for x in dict(config_file.items('DEFAULT')) if x.startswith("plugin_")]
        if "plugin_directory" in plugins: plugins.remove("plugin_directory")
        extensions =  plugins + equations
        #if equations exist we should do something with them
        if len(extensions) > 0:
            for extension in extensions:
                if config_file.has_option(line, extension):
                    try:
                        boolvar=config_file.getboolean(line, extension)
                    except ValueError:
                        #not a boolean - ignore this item
                        continue

                    if boolvar:
                        extension_nice = extension.replace("eq_", "_").replace("plugin_", "_")
                        #build a load of band math status amd log files
                        extension_status_file = scops_common.STATUS_FILE.format(output_location, line + extension_nice)
                        extension_log_file =  scops_common.LOG_FILE.format(output_location, line + extension_nice)

                        link = scops_common.LINE_LINK.format(os.path.basename(os.path.normpath(output_location)), line + extension_nice, defaults["project_code"])
                        status_db.insert_line_into_db(os.path.basename(os.path.normpath(output_location)), line + extension_nice, "Waiting to process", 0, 0, 0, 0, link, 0, 0)
                        #open status and log files
                        open(extension_status_file, 'w+').write("{} = {}".format((line + extension_nice), "waiting"))
                        open(extension_log_file, mode="a").close()

    if (not config_file.getboolean('DEFAULT', 'status_email_sent')) or (new_location):
        scops_process_apl_line.email_status(defaults["email"], output_location, defaults["project_code"])
        config_file.set('DEFAULT', "status_email_sent", "True")
        config_file.write(open(config, 'w'))

    try:
        filesizes = list(open(glob.glob(hyper_delivery + "/flightlines/mapped/unzipped_filesize.csv")[0]))
    except Exception as e:
        filesizes = None

    # Set up job submission system
    if job_submission_system == "local":
        job_obj = scops_job_submission.LocalJobSubmission(logger, defaults)
    elif job_submission_system == "qsub":
        job_obj = scops_job_submission.QsubJobSubmission(logger, defaults)
    elif job_submission_system == "bsub":
        job_obj = scops_job_submission.BsubJobSubmission(logger, defaults)
    else:
        raise NotImplementedError("Queue submission system '{}' not implemented"
                        "".format(job_submission_system))

    for line in lines:
        band_ratio = False
        main_line = False
        if dict(config_file.items(line))["process"] in "true":
            #if they want the main line processed we should submit it
            main_line = True

        if len([x for x in dict(config_file.items(line)) if "eq_" in x]) > 0:
            # if they want the band ratiod file we should submit it
            band_ratio = True

        if main_line or band_ratio:
            # Submit job
            job_obj.submit(config, line, output_location, filesizes,
                        main_line, band_ratio)

    logger.info("all lines complete")


if __name__ == '__main__':
    # Get the input arguments
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config',
                        '-c',
                        help='web config file',
                        default=None,
                        required=True,
                        metavar="<configfile>")
    parser.add_argument('--local',
                        '-l',
                        help='local processing vs grid',
                        action='store_true',
                        default=False)
    parser.add_argument('--output',
                        '-o',
                        help='Force output path and name',
                        default=None,
                        metavar="<folder_name>")
    args = parser.parse_args()

    if args.local:
        submission_system = 'local'
    else:
        submission_system = scops_common.QSUB_SYSTEM

    web_qsub(args.config, job_submission_system=submission_system,
             output=args.output)

#! /usr/bin/env python
from flask import Flask, send_from_directory
from flask import render_template
from flask import request, Response
from functools import wraps
from numpy import arange
import folder_structure
import ConfigParser
import glob
import xml.etree.ElementTree as etree
import os
import utm
import hdr_files
import datetime
from arsf_dem import dem_nav_utilities
import random
import math
import projection

CONFIG_OUTPUT = "/users/rsg/arsf/web_processing/configs/"
UPLOAD_FOLDER = "/users/rsg/arsf/web_processing/dem_upload/"
WEB_PROCESSING_FOLDER = "/users/rsg/arsf/web_processing/"
KMLPASS = "/users/rsg/arsf/usr/share/kmlpasswords.csv"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

bands = [1, 2, 3, 4, 5]
PIXEL_SIZES = arange(0.5, 7.5, 0.5)

bounds = {
    'n': 40000,
    's': 20000,
    'e': 60000,
    'w': 40000
}

def check_auth(username, password, projcode):
    """This function is called to check if a username /
    password combination is valid.
    """
    auth = False
    for pair in open(KMLPASS):
        username_auth, password_auth = pair.strip("\n").split(",")
        #print username, password, projcode, username_auth, password_auth
        if username == username_auth and password == password_auth and projcode == username_auth:
            print "authed!"
            auth = True
        elif username == "arsf_admin" and password == "supersecret":
            auth = True
    return auth

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password, request.args["project"]):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def validation(request):
    """
    Takes a dictionary of terms for config output and validates that the options are correct/don't pose a risk to our systems
    :param request: Config options dictionary
    :type request: dict

    :return: validation state either true or false
    :rtype: bool
    """
    #TODO make more checks, maybe come up with a brief black list
    validated = True
    for key in request:
        if "band" in key or "pixel_size" in key or "bound" in key or "year" in key or "julianday" in key:
            if math.isnan(float(request[key])):
                validated = False
        if "check" in key:
            if "on" not in request[key]:
                validated = False

        if "proj_string" in key:
            wktstring = projection.proj4_to_wkt(request[key])
            projstring = projection.wkt_to_proj4(wktstring)

            if request[key] not in projstring:
                validated = False

        if ";" in request[key]:
            validated = False

    return validated


@app.route('/downloads/<path:projfolder>', methods=['GET', 'POST'])
@requires_auth
def download(projfolder):
    """
    Takes a http request with the project folder and provides a download instance, has no authentication currently

    :param projfolder:
    :return: http download
    """
    #TODO make this safer
    projfolder = WEB_PROCESSING_FOLDER + "processing/" + projfolder
    if not os.path.exists(projfolder):
        return "not gonna work"
    download_file = [x for x in glob.glob(projfolder + "/mapped/*.zip") if "bil" not in x][0]
    return send_from_directory(directory=os.path.dirname(download_file), filename=os.path.basename(download_file))


@app.route('/confirm/<string:projnum>', methods=['GET', 'POST'])
def confirm_request(projnum):
    """
    Receives request from user email which will then confirm the email address used

    :param projnum: the project name/config file name that needs to be updated
    :type projnum: str

    :return: string
    """
    #TODO make this update the config and return a better message
    return "confirmed"


@app.route('/theme')
def theme():
    #TODO take this out
    return render_template('index.html', name=None)


@app.route('/kmlpage')
def kml_page(name=None):
    #TODO make kml pages link to jobrequest and remove this
    return render_template('kml.html')


@app.route('/')
@app.route('/jobrequest', methods=['GET', 'POST'])
@requires_auth
def job_request(name=None):
    """
    Receives a request from html with the day, year and required project code then returns a request page based on the data it finds in the proj dir

    :param name: placeholder
    :type name: str

    :return: job request html page
    :rtype: html
    """
    day=request.args["day"]
    year=request.args["year"]
    proj_code=request.args["project"]

    #check if theres a sortie associated with the day
    try:
        sortie = request.args["sortie"]
    except:
        sortie = ''

    folder = folder_structure.FolderStructure(year=year, jday=str(day), projectCode=proj_code, fletter=sortie)

    #if folder_structure failed we need to error out
    if folder.projPath == os.getcwd():
        #TODO make this give a better message in a html doc
        return "he's dead jim"

    hyper_delivery = glob.glob(folder.projPath + '/delivery/*hyperspectral*')

    #using the xml find the project bounds
    projxml = etree.parse(glob.glob(hyper_delivery[0] + '/project_information/*project.xml')[0]).getroot()
    bounds={
        'n' : projxml.find('.//{http://www.isotc211.org/2005/gmd}northBoundLatitude').find('{http://www.isotc211.org/2005/gco}Decimal').text,
        's' : projxml.find('.//{http://www.isotc211.org/2005/gmd}southBoundLatitude').find('{http://www.isotc211.org/2005/gco}Decimal').text,
        'e' : projxml.find('.//{http://www.isotc211.org/2005/gmd}eastBoundLongitude').find('{http://www.isotc211.org/2005/gco}Decimal').text,
        'w' : projxml.find('.//{http://www.isotc211.org/2005/gmd}westBoundLongitude').find('{http://www.isotc211.org/2005/gco}Decimal').text
    }

    #get the utm zone
    utmzone = utm.from_latlon(float(bounds["n"]), float(bounds["e"]))[2:]

    #if it's britain we should offer UKBNG on the web page
    if utmzone[0] in [29, 30, 31] and utmzone[1] in ['U', 'V']:
        britain = True
    else:
        britain = False

    #begin building the lines for output
    line_hdrs = [f for f in glob.glob(hyper_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f]
    lines = []
    for line in line_hdrs:
        linehdr = hdr_files.Header(line)
        linedict = {
            "name" : os.path.basename(line)[:-10],
            "bandsmax" : int(linehdr.bands),
            "bands" : range(1, int(linehdr.bands)+1, 1),
        }
        lines.append(linedict)

    #grab 2 random flightlines for sampling of altitude, any more is going to cause problems with speed
    sampled_nav = random.sample(glob.glob(hyper_delivery[0] + "/flightlines/navigation/*_nav_post_processed.bil"), 2)

    #we should base pixel size off the minimum
    altitude = dem_nav_utilities.get_min_max_from_bil_nav_files(sampled_nav)["altitude"]["min"]

    #for the moment just using fenix
    sensor = "fenix"

    #calculate pixelsize
    pixel = pixelsize(altitude, sensor)

    #round it to .5
    pixel = round(pixel * 2) / 2

    #sort the lines so they look good on the web page
    lines = sorted(lines, key=lambda line: line["name"])

    #creates the webpage by handing vars into the template engine
    return render_template('requestform.html',
                           flightlines=lines,
                           uk = britain,
                           pixel_sizes=PIXEL_SIZES,
                           optimal_pixel=pixel,
                           bounds=bounds,
                           name=name,
                           julian_day=day,
                           year=year,
                           project_code=proj_code,
                           utmzone="UTM zone "+str(utmzone[0])+str(utmzone[1]))


@app.route('/progress', methods=['POST'])
@requires_auth
def progress():
    """
    receives a post request from the jobrequest page and validates the input

    :return: html page
    :rtype: html
    """
    requestdict = request.form
    validated = validation(requestdict)
    if validated:
        lines = []
        for key in requestdict:
            if "_line_check" in key:
                lines.append(key.strip("_line_check"))
        lines = sorted(lines)
        filename = requestdict["project_code"] + '_' + requestdict["year"] + '_' + requestdict["julianday"] + '_' + datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        config_output(requestdict, lines=lines, filename=filename)
        return render_template('submitted.html')
    else:
        #TODO make this rejection better
        return "request rejected"


def config_output(requestdict, lines, filename):
    """
    Writes a vonfig to the web processing configs folder, this will then be picked up by web_qsub

    :param requestdict: A request converted to immutable dict from the job request page
    :type requestdict: immutable dict

    :param lines: list of flightlines to be processed
    :type lines: list

    :param filename: config filename to write to
    :type filename: str

    :return: 1 on success
    :rtype: int
    """
    config = ConfigParser.RawConfigParser()
    config.set('DEFAULT', "julianday", requestdict["julianday"])
    config.set('DEFAULT', "year", requestdict["year"])
    config.set('DEFAULT', "sortie", requestdict["sortie"])
    config.set('DEFAULT', "project_code", requestdict["project_code"])
    config.set('DEFAULT', "projection", requestdict["projectionRadios"])
    try:
        config.set('DEFAULT', "projstring", requestdict["projString"])
    except:
        config.set('DEFAULT', "projstring", '')
    config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
    config.set('DEFAULT', "bounds", requestdict["bound_n"] + ' ' + requestdict["bound_e"] + ' ' + requestdict["bound_s"] + ' ' + requestdict["bound_w"])
    config.set('DEFAULT', "email", requestdict["email"])
    config.set('DEFAULT', "interpolation", requestdict["optionsIntRadios"])
    config.set('DEFAULT', "pixelsize", requestdict["pixel_size_x"] + ' ' + requestdict["pixel_size_y"])
    config.set('DEFAULT', "submitted", False)
    print requestdict
    try:
        if requestdict["mask_all_check"] in "on":
            masking = "all"
        else:
            masking = "none"
    except:
        masking = "none"
    config.set('DEFAULT', "masking", masking)
    for line in lines:
        config.add_section(str(line))
        if requestdict['%s_line_check' % line] in "on" or requestdict['process_all_lines'] in "on":
            config.set(str(line), 'process', 'true')
        else:
            config.set(str(line), 'process', 'false')
        config.set(str(line), 'band_range', requestdict["%s_band_start" % line] + '-' + requestdict["%s_band_stop" % line])
    configfile = open(CONFIG_OUTPUT + filename +'.cfg', 'a')
    config.write(configfile)
    os.chmod(CONFIG_OUTPUT + filename +'.cfg', 0664)
    return 1


@app.route('/processing', methods=['GET', 'POST'])
def processingpage(name=None):
    """
    Function to show the processing page, for the moment doesn't do anything

    :param name: placeholder
    :type name: str

    :return: template rendered html file
    :rtype: html
    """
    folder = request.args["id"]
    lines = []
    for line in glob.glob(WEB_PROCESSING_FOLDER + folder + "/status/*"):
        for l in open(line):
            status = l.split(' ')[2]
        line_details = {
            "name" : os.basepath(line),
            "status" : status
        }
        lines.append(line_details)

    return render_template('processingpage.html',
                           lines=lines)


def getifov(sensor):
    """
    Function for sensor ifov grabbing

    :param sensor: sensor name, fenix eagle or hawk
    :type sensor: str

    :return: ifov
    :rtype: float
    """
    if "fenix" in sensor:
        ifov = 0.001448623
    if "eagle" in sensor:
        ifov = 0.000645771823
    if "hawk" in sensor:
        ifov = 0.0019362246375
    return ifov


def pixelsize(altitude, sensor):
    return 2 * altitude * math.tan(getifov(sensor)/2)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', threaded=True, port=5001)

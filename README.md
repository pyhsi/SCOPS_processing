# The Simple Concurrent Online Processing System (SCOPS) #

## Installation ##

### Pre-requsites ###

* APL (https://github.com/arsf/apl / https://nerc-arf-dan.pml.ac.uk/trac/wiki/Downloads/software/)
* NERC-ARF DEM Scripts (https://github.com/pmlrsg/arsf_dem_scripts)
* GDAL
* NumExpr (https://github.com/pydata/numexpr)

APL and NERC-ARF DEM scripts will need to be installed from source, GDAL and NumExpr can be installed using your package manager.

### SCOPS ###

To install use:
```
python setup.py install
```
By default this will install to `/usr/local`, you can override this by setting `--prefix`.


## Config ##

For SCOPS to work on your system a number of environmental variables need to be set.
The following is an illustration of the set up required for setup on JASMIN.

```bash
export ERROR_EMAIL=me@my.domain # Email to send error messages to
export WEB_CONFIG_DIR=/home/users/dac/arsf_group_workspace/dac/web_processor_test/configs/ # Directory for config files
export WEB_OUTPUT=/home/users/dac/arsf_group_workspace/dac/web_processor_test/processing/ # Directory for ouput foles
export QSUB_LOG_DIR=/home/users/dac/arsf_group_workspace/dac/web_processor_test/logs/  # Directory for log files
export HYPER_DELIVERY_FOLDER=/hyperspectral # Directory hyperspectral delivery files are stored within
export TEMP_PROCESSING_DIR="" # Directory for local temporary processing (if not set will use WEB_OUTPUT"
export QSUB_SYSTEM=bsub  # System to use for submitting jobs, e.g, bsub, qsub, or local for local processing
export QUEUE=short-serial # Queue to use for jobs
```

# OpenDOAR

This software package contains the OpenDOAR branded discovery interface and the OpenDOAR admin interface, which work off the OARR back-end

## Installation

### Dependencies

1. A running instance of [OARR](http://github.com/CottageLabs/oarr)
2. ElastiSearch

### Process

1. Install an instance of ElasticSearch
2. Install [OARR](http://github.com/CottageLabs/oarr) if required, as per its installation instructions
3. Obtain a [username and api key](http://github.com/CottageLabs/oarr) on behalf of this application from OARR.
4. Customise the settings for this application to point to the correct OARR_API_BASE_URL and OARR_API_KEY
5. Create a virtual environment for this application
6. Install this application into the virtual environment ("pip install -e .")
7. Start in the standard flask webapp container with

    python portality/app.py

### Data Migration

When setting this up, you should consider migrating data from [OpenDOAR](http://opendoar.org) and [ROAR](http://roar.eprints.org) as detailed at the following links:

* [https://github.com/CottageLabs/oarr#initial-data-migration](https://github.com/CottageLabs/oarr#initial-data-migration)
* [https://github.com/CottageLabs/roar2doar](https://github.com/CottageLabs/roar2doar)



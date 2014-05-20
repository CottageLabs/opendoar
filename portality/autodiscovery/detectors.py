import requests, re, logging, socket, pycountry
from incf.countryutils import transformations
from urlparse import urlparse

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

class Detector(object):
    def name(self):
        return "Abstract Detector"
    def detectable(self, register):
        return False
    def detect(self, register, info):
        pass

class OperationalStatus(Detector):
    """Attempts to determine if the repository is operational"""

    ip_rx = "(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"

    def name(self):
        return "Operational Status"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        """
        Operational - has readable url with no port number and responds to get
        Trial - has url with ip and/or port number and responds to get
        Broken - does not respond to get or responds with an error code
        """
        url = register.repo_url

        try:
            resp = requests.get(url, timeout=5)
            info["url_get"] = resp
        except:
            register.operational_status = "Broken"
            return

        if resp.status_code != requests.codes.ok:
            register.operational_status = "Broken"
            return

        pn = self._has_port_number(url)
        ip = self._is_ip(url)

        if pn or ip:
            register.operational_status = "Trial"

        # operation status is Operational
        register.operational_status = "Operational"

    def _has_port_number(self, url):
        parsed = urlparse(url)
        if ":" in parsed.netloc:
            # port number is present
            return True
        return False

    def _is_ip(self, url):
        parsed = urlparse(url)
        m = re.search(self.ip_rx, parsed.netloc)
        return m is not None

class Country(Detector):
    hostip_api = "http://api.hostip.info/get_json.php"

    tld_map = {
        "uk" : "gb", # uk tld refers to gb in iso 3166-1
        "edu" : "us", # edu is almost completely us based
        "tp" : "tl" # old and new tlds for Timor
    }

    ignore_tld = ["eu"]

    def name(self):
        return "Country"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # our first best bet is to get the cctld off the url
        url = register.repo_url
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0] # ensure we get rid of the port
        tld = host.split(".")[-1] # the final part of the domain

        # map the tld to the iso 3166-1 form if necessary
        tld = self.tld_map.get(tld.lower(), tld)

        try:
            c = pycountry.countries.get(alpha2=tld.upper())
            register.set_country(name=c.name, code=c.alpha2)
            return
        except KeyError:
            pass

        # if we get down to here we have to try and geolocate the ip
        ip = socket.gethostbyname(parsed.netloc)
        r = self.hostip_api + "?ip=" + ip
        resp = requests.get(r)
        j = resp.json()
        code = j.get("country_code")
        try:
            c = pycountry.countries.get(alpha2=code.upper())
            register.set_country(name=c.name, code=c.alpha2)
            return
        except KeyError:
            pass

class Continent(Detector):
    def name(self):
        return "Continent"

    def detectable(self, register):
        return register.country_code is not None

    def detect(self, register, info):
        code = register.country_code
        continent_code = transformations.cca_to_ctca2(code)
        continent = transformations.cca_to_ctn(code)
        register.set_continent(name=continent, code=continent_code)

#############################################################
# List of detectors and the order they should run
#############################################################

GENERAL = [
    OperationalStatus,
    Country,
    Continent
]
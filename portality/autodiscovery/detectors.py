import requests, re, logging
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
    def detect(self, register):
        pass

class OperationalStatus(Detector):
    """Attempts to determine if the repository is operational"""

    ip_rx = "(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"

    def name(self):
        return "Operational Status"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register):
        """
        Operational - has readable url with no port number and responds to get
        Trial - has url with ip and/or port number and responds to get
        Broken - does not respond to get or responds with an error code
        """
        url = register.repo_url

        try:
            resp = requests.get(url, timeout=5)
        except:
            register.operational_status = "Broken"

        if resp.status_code != requests.codes.ok:
            register.operational_status = "Broken"

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


#############################################################
# List of detectors and the order they should run
#############################################################

GENERAL = [
    OperationalStatus
]
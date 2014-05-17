from portality.autodiscovery import detectors
from portality.oarr import Register
import logging

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

def discover(url):
    r = Register()
    r.repo_url = url

    # for each general (i.e. non repo-type specific detector) check to see if the register contains
    # enough info for the detector to run, and then run it if so
    for klazz in detectors.GENERAL:
        detector = klazz()
        if detector.detectable(r):
            log.info(url + " - " + detector.name())
            detector.detect(r)

    return r
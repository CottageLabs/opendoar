from portality.autodiscovery import detectors, registryfile
from portality.oarr import Register
import logging

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

def discover(url, raise_registry_file_error=True):
    if not url.startswith("http"):
        url = "http://" + url

    # first try to detect the registry file
    try:
        r = registryfile.RegistryFile.get(url)
        if r is not None:
            return r
    except registryfile.RegistryFileException as e:
        if raise_registry_file_error:
            raise e

    # if we get here, the registry file may have failed or it may not have existed
    # in which case we fall back to auto-detect
    r = Register()
    r.repo_url = url

    # for each general (i.e. non repo-type specific detector) check to see if the register contains
    # enough info for the detector to run, and then run it if so
    info = detectors.Info()
    for klazz in detectors.GENERAL:
        detector = klazz()
        if detector.detectable(r):
            log.info(url + " - " + detector.name())
            try:
                detector.detect(r, info)
            except Exception as e:
                log.info(e.message)

    return r
from portality.autodiscovery import detectors, registryfile
from portality.oarr import Register
import logging, requests

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

def validate_registry_file(repo_url=None, registry_file_url=None, registry_file_content=None):
    cont = None
    source = None

    if repo_url is not None:
        resp = registryfile.RegistryFile.autodetect(repo_url)
        if resp is not None:
            cont = resp.text
            source = repo_url
    elif registry_file_url is not None:
        resp = registryfile.RegistryFile.retrieve(registry_file_url)
        if resp is not None:
            cont = resp.text
            source = registry_file_url
    elif registry_file_content is not None:
        cont = registry_file_content
        source = "supplied content"

    if cont is None:
        raise registryfile.RegistryFileException("validation error", ["Unable to obtain a registry file/its content to validate"])

    obj = registryfile.RegistryFile.validate(cont, source)
    return obj

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
import os, json, requests
from unittest import TestCase
from portality.autodiscovery import registryfile
from portality import oarr

BASE_FILE_PATH = os.path.dirname(os.path.realpath(__file__))
REGISTRY_FILE_RESOURCES = os.path.join(BASE_FILE_PATH, "resources", "registryfile")

OARR_VALID = os.path.join(REGISTRY_FILE_RESOURCES, "oarr-valid.json")
OARR_SCHEMA_INVALID = os.path.join(REGISTRY_FILE_RESOURCES, "oarr-schema-invalid.json")
OARR_BROKEN = os.path.join(REGISTRY_FILE_RESOURCES, "oarr-broken.json")
OARR_EMPTY = os.path.join(REGISTRY_FILE_RESOURCES, "oarr-empty.json")
OARR_NO_DEFAULT = os.path.join(REGISTRY_FILE_RESOURCES, "oarr-no-default.json")

expected_messages_for_total_failure = [
    "last updated date is not of the form YYYY-mm-ddTHH:MM:SSZ : yesterday",
    "identifier for object being replaced must take the form of the info uri (info:oarr:<identifier>) 123456789",
    "operational_status must be one of ['Trial', 'Operational'] but is Etherial",
    "lang for metadata record must be set",
    "lang fr is repeated in list of metadata records",
    "Two or more metadata records are marked as default",
    "No record entry in the metadata object, or record entry is empty",
    "No record entry in the metadata object, or record entry is empty",
    "No record entry in the metadata object, or record entry is empty",
    "metadata record language english is not recognised as an iso-639-1 language code",
    "country code uk is not recognised as an iso-3166-1 country code",
    "established date thursday is not a number; should be a 4 digit year",
    "content language welsh is not recognised as an iso-639-1 language code",
    "content language franglais is not recognised as an iso-639-1 language code",
    "default metadata record does not contain the repository url",
    "established date 2100 is in the future",
    "url domain does not look complete http://cottagelabs",
    "established date 1600 is too far in the past",
    "the name of the software is not present",
    "url domain does not look complete http://dspace",
    "contact does not contain a details object, or details object is empty",
    "contact does not contain a details object, or details object is empty",
    "contact's latitude and longitude must both be specified",
    "contact's latitude and longitude must both be specified",
    "contact's latitude is not numeric: north a bit",
    "contact's longitude is not numeric: west a bit",
    "contact's latitude is outside the allowable range (-90 -> 90): 500.9",
    "contact's longitude is outside the allowable range (-180 -> 180): 932.4",
    "organisation does not contain a details object or details object is empty",
    "organisation does not contain a details object or details object is empty",
    "url domain does not look complete http://cottagelabs",
    "url domain does not look complete http://cottagelabs",
    "in organisation, country code london is not recognised as an iso-3166-1 country code",
    "organisation's latitude and longitude must both be specified",
    "organisation's latitude and longitude must both be specified",
    "organisation's latitude is not numeric: north a bit",
    "organisation's longitude is not numeric: west a bit",
    "organisation's latitude is outside the allowable range (-90 -> 90): 500.9",
    "organisation's longitude is outside the allowable range (-180 -> 180): 932.4",
    "policy must specify a policy type",
    "policy must contain one or more policy terms",
    "api entry must specify a type",
    "api entry must specify a base url",
    "url domain does not look complete http://sword",
    "metadata_format can only be present for apis of type oai-pmh",
    "accepts can only be present for apis of type sword",
    "accept_packaging can only be present for apis of type sword",
    "integration section must specify integrated_with",
    "url domain does not look complete http://cris"
]

### Mocks ###########################

class MockResponse(object):
    def __init__(self, text, flagged=False):
        self.text = text
        self.status_code = 200
        self.flagged = flagged

def html_autodiscovery(url, *args, **kwargs):
    if url.endswith("myoarr.json"):
        f = open(OARR_VALID)
        return MockResponse(f.read(), True)
    else:
        return MockResponse("""
        <html><head><link rel='oarr' type='application/json' href='/myoarr.json'></head><body></body></html>
        """)

def guess_autodiscovery(url, *args, **kwargs):
    if url.endswith("/oarr.json"):
        f = open(OARR_VALID)
        return MockResponse(f.read(), True)
    else:
        return MockResponse("""
        <html><head></head><body></body></html>
        """)

def fail_autodiscovery(url, *args, **kwargs):
    if url.endswith("/oarr.json"):
        resp = MockResponse("", True)
        resp.status_code = 404
        return resp
    else:
        return MockResponse("""
        <html><head></head><body></body></html>
        """)

def malformed_autodiscovery(url, *args, **kwargs):
    if url.endswith("/oarr.json"):
        resp = MockResponse("a;ijdfjewfwlkejfwkjefwijf", True)
        return resp
    else:
        return MockResponse("""
        <html><head></head><body></body></html>
        """)

def invalid_autodiscovery(url, *args, **kwargs):
    if url.endswith("myoarr.json"):
        f = open(OARR_BROKEN)
        return MockResponse(f.read(), True)
    else:
        return MockResponse("""
        <html><head><link rel='oarr' type='application/json' href='/myoarr.json'></head><body></body></html>
        """)

### Utils ############################

def read_json(path):
    f = open(path)
    return json.loads(f.read())

class TestRegistryFile(TestCase):

    def setUp(self):
        self.requests_get = requests.get

    def tearDown(self):
        requests.get = self.requests_get

    def test_01_schema_validate(self):
        # a valid schema, should return true
        obj = read_json(OARR_VALID)
        valid, messages = registryfile.RegistryFile.schema_validate(obj)
        assert valid
        assert len(messages) == 0

        # an invalid schema - should return false
        obj = read_json(OARR_SCHEMA_INVALID)
        valid, messages = registryfile.RegistryFile.schema_validate(obj)
        assert not valid
        assert len(messages) == 1

    def test_02_content_valid(self):
        obj = read_json(OARR_VALID)
        valid, messages = registryfile.RegistryFile.content_validate(obj)
        assert valid
        assert len(messages) == 0

    def test_03_content_invalid(self):
        obj = read_json(OARR_BROKEN)

        # first, be clear that this file passes schema validation
        valid, messages = registryfile.RegistryFile.schema_validate(obj)
        assert valid

        # now show that it fails content validation
        valid, messages = registryfile.RegistryFile.content_validate(obj)
        assert not valid
        assert len(messages) == len(expected_messages_for_total_failure)
        for msg in expected_messages_for_total_failure:
            assert msg in messages

    def test_04_content_empty(self):
        obj = read_json(OARR_EMPTY)

        # first, be clear that this file passes schema validation
        valid, messages = registryfile.RegistryFile.schema_validate(obj)
        assert valid

        # now show that it fails content validation
        valid, messages = registryfile.RegistryFile.content_validate(obj)
        assert not valid

    def test_05_no_default_metadata(self):
        obj = read_json(OARR_NO_DEFAULT)

        # first, be clear that this file passes schema validation
        valid, messages = registryfile.RegistryFile.schema_validate(obj)
        assert valid

        # now show that it fails content validation
        valid, messages = registryfile.RegistryFile.content_validate(obj)
        assert not valid

    def test_06_autodiscovery_link(self):
        requests.get = html_autodiscovery
        resp = registryfile.RegistryFile.autodetect("http://cottagelabs.com")
        assert isinstance(resp, MockResponse)
        assert resp.flagged # tells us we hit the oarr file - see the html_autodiscovery method above

    def test_07_autodiscovery_guess(self):
        requests.get = guess_autodiscovery
        resp = registryfile.RegistryFile.autodetect("http://cottagelabs.com")
        assert isinstance(resp, MockResponse)
        assert resp.flagged # tells us we hit the oarr file - see the guess_autodiscovery method above

    def test_08_autodiscovery_fail(self):
        requests.get = fail_autodiscovery
        resp = registryfile.RegistryFile.autodetect("http://cottagelabs.com")
        assert resp is None

    def test_09_no_file(self):
        requests.get = fail_autodiscovery
        file = registryfile.RegistryFile.get("http://cottagelabs.com")
        assert file is None

    def test_10_malformed_file(self):
        requests.get = malformed_autodiscovery
        with self.assertRaises(registryfile.RegistryFileException):
            try:
                file = registryfile.RegistryFile.get("http://cottagelabs.com")
            except registryfile.RegistryFileException as e:
                assert e.message == "error reading file"
                raise e

    def test_11_get_success(self):
        requests.get = html_autodiscovery
        file = registryfile.RegistryFile.get("http://cottagelabs.com")
        assert isinstance(file, oarr.Register)
        assert file.get_repo_name() == "Cottage Labs"

    def test_12_get_invalid(self):
        requests.get = invalid_autodiscovery
        with self.assertRaises(registryfile.RegistryFileException):
            try:
                file = registryfile.RegistryFile.get("http://cottagelabs.com")
            except registryfile.RegistryFileException as e:
                assert e.message == "error validating file"
                assert len(e.errors) == len(expected_messages_for_total_failure)
                for msg in expected_messages_for_total_failure:
                    assert msg in e.errors
                raise e
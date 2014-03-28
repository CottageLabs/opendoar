import requests
from copy import deepcopy

class OARRClient(object):
    def __init__(self, base_url):
        self.base_url = base_url
        if not self.base_url.endswith("/"):
            self.base_url += "/"
    
    def get_record(self, record_id):
        resp = requests.get(self.base_url + "/record/" + record_id)
        return Register(resp.json())

class Register(object):
    def __init__(self, raw):
        self.raw = raw
    
    @property
    def register(self):
        return self.raw.get("register", {})
    
    def get_metadata(self, lang):
        # FIXME: full implementation will be required for full multi-lingual support
        default = None
        for md in self.raw.get("register", {}).get("metadata", []):
            if md.get("lang") == lang:
                return deepcopy(md.get("record"))
            if md.get("default", False):
                default = md
        return deepcopy(default) # if we couldn't find the language you were looking for, return the default

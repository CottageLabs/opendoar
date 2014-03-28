import requests
from copy import deepcopy
from datetime import datetime

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
    
    @property
    def created_date(self):
        return self.raw.get("created_date")
    
    def get_created_date(self, form):
        return datetime.strftime(datetime.strptime(self.created_date, "%Y-%m-%dT%H:%M:%SZ"), form)
    
    @property
    def last_updated(self):
        return self.raw.get("last_updated")
    
    def get_last_updated(self, form):
        return datetime.strftime(datetime.strptime(self.last_updated, "%Y-%m-%dT%H:%M:%SZ"), form)
    
    def get_metadata(self, lang):
        # FIXME: full implementation will be required for full multi-lingual support
        default = None
        for md in self.raw.get("register", {}).get("metadata", []):
            if md.get("lang") == lang:
                return deepcopy(md.get("record"))
            if md.get("default", False):
                default = md
        return deepcopy(default) # if we couldn't find the language you were looking for, return the default

import requests, json
from copy import deepcopy
from datetime import datetime

class OARRClient(object):
    def __init__(self, base_url):
        self.base_url = base_url
        if not self.base_url.endswith("/"):
            self.base_url += "/"
    
    def get_record(self, record_id):
        try:
            resp = requests.get(self.base_url + "/record/" + record_id)
            return Register(resp.json())
        except:
            return None
    
    def get_org(self, org):
        qry = {
            "query":{
                "term": {
                    "register.organisation.details.name.exact": org
                }
            },
            "size":1000
        }
        try:
            resp = requests.get(self.base_url + "/query?source=" + json.dumps(qry))
            return Org(resp.json(), org)
        except:
            return None


class Register(object):
    def __init__(self, raw):
        self.raw = raw
    
    @property
    def json(self):
        return json.dumps(self.raw)
    
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
        
        
class Org(object):
    def __init__(self, raw, orgname):
        self.raw = raw
        self.organisation = orgname
            
    @property
    def record(self):
        rec = {
            'name': self.organisation,
            'created_date': [],
            'last_updated': [],
            'units': [],
            'repos': []
        }
        for row in [i['_source'] for i in self.raw.get('hits',{}).get('hits',[])]:
            for o in row['register']['organisation']:
                if o['details']['name'] == self.organisation:
                    org = o
            if 'url' not in rec.keys():
                try:
                    rec['url'] = org['details']['url']
                except:
                    pass
            if 'lat' not in rec.keys():
                try:
                    rec['lat'] = org['details']['lat']
                except:
                    pass
            if 'lon' not in rec.keys():
                try:
                    rec['lon'] = org['details']['lon']
                except:
                    pass
            try:
                if org['details']['unit'] not in rec['units']:
                    rec['units'].append(org['details']['unit'])
            except:
                pass
            try:
                # TODO: some sort of change may be required later if we end up 
                # with multilingual lists of metadata objects
                rec['repos'].append(row['register']['metadata'][0])
                rec['repos'][-1]['id'] = row['id']
            except:
                pass
            rec['created_date'].append(row['created_date'])
            rec['last_updated'].append(row['last_updated'])
        rec['created_date'] = sorted(rec['created_date'])[0]
        rec['last_updated'] = sorted(rec['last_updated'])[-1]
        return rec
    
    @property
    def json(self):
        return json.dumps(self.record)
        
    @property
    def units(self):
        return self.record['units']
        
    @property
    def contacts(self):
        return self.record['contacts']
        
    @property
    def contact_emails(self):
        return [c['details']['email'] for c in self.contacts]
        
    @property
    def repos(self):
        return self.record['repos']
        
    @property
    def repo_ids(self):
        return [c['id'] for c in self.repos]
        
    @property
    def created_date(self):
        return self.record.get("created_date")
    
    def get_created_date(self, form):
        return datetime.strftime(datetime.strptime(self.created_date, "%Y-%m-%dT%H:%M:%SZ"), form)
    
    @property
    def last_updated(self):
        return self.record.get("last_updated")
    
    def get_last_updated(self, form):
        return datetime.strftime(datetime.strptime(self.last_updated, "%Y-%m-%dT%H:%M:%SZ"), form)
    




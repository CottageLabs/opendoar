import requests, json, pycountry, StringIO
from copy import deepcopy
from datetime import datetime
from csv import reader
from datetime import datetime

class OARRClientException(Exception):
    pass

class OARRClient(object):
    def __init__(self, base_url, api_key=False):
        self.base_url = base_url
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        self.api_key = api_key
    
    def get_record(self, record_id):
        try:
            resp = requests.get(self.base_url + "/record/" + record_id)
            return Register(resp.json())
        except:
            return None

    def save_record(self, record={}, record_id=""):
        if not self.api_key:
            return False
        else:
            try:
                if "id" in record and record_id == "": record_id = record["id"]
                if "admin" not in record: record["admin"] = {}
                if "opendoar" not in record["admin"]: record["admin"]["opendoar"] = {}
                record["admin"]["opendoar"]["last_saved"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                addr = self.base_url + "record"
                if record_id: addr += '/' + record_id
                addr += '?api_key=' + self.api_key
                resp = requests.post(addr, data=json.dumps(record))
                if resp.json()["success"]:
                    if record_id == "": record_id = resp.json()["id"]
                    return record_id
                else:
                    return False
            except:
                return False

    def delete_record(self, record_id):
        addr = self.base_url + "record/" + record_id + '?api_key=' + self.api_key
        resp = requests.delete(addr)
        return True

    def prep_record(self,record,request):
        return _prep_record(record,request)

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

    def query(self, qry={
        'query':{'match_all':{}},
        'size': 0,
        'facets':{}
    }):
        try:
            resp = requests.get(self.base_url + "/query?source=" + json.dumps(qry) )
            return resp.json()
        except:
            return {}


class Register(object):
    def __init__(self, raw=None):
        self.raw = raw if raw is not None else {}
    
    @property
    def json(self):
        return json.dumps(self.raw)
    
    @property
    def register(self):
        return self.raw.get("register", {})

    def ensure_register(self):
        if "register" not in self.raw:
            self.raw["register"] = {}

    @property
    def repo_url(self):
        return self.get_metadata_value("url")

    @repo_url.setter
    def repo_url(self, url):
        self.set_metadata_value("url", url, "en")

    @property
    def operational_status(self):
        return self.register.get("operational_status")

    @operational_status.setter
    def operational_status(self, val):
        if val not in ["Operational", "Trial", "Broken", "Closed"]:
            # raise OARRClientException("Operational satus must be one of Operational, Trial, Broken or Closed")
            print "WARNING: Operational satus should be one of Operational, Trial, Broken or Closed"
        self.ensure_register()
        self.register["operational_status"] = val

    @property
    def repo_name(self):
        return self.get_repo_name("en")

    def get_repo_name(self, lang="en"):
        return self.get_metadata_value("name", lang)

    @repo_name.setter
    def repo_name(self, val):
        self.set_repo_name(val, "en")

    def set_repo_name(self, val, lang="en"):
        self.set_metadata_value("name", val, lang)

    @property
    def description(self):
        return self.get_description("en")

    def get_description(self, lang="en"):
        return self.get_metadata_value("description", lang)

    @description.setter
    def description(self, val):
        self.set_description(val, "en")

    def set_description(self, val, lang="en"):
        self.set_metadata_value("description", val, lang)

    @property
    def twitter(self):
        return self.get_metadata_value("twitter")

    @twitter.setter
    def twitter(self, val):
        self.set_metadata_value("twitter", val)

    @property
    def country(self):
        return self.get_metadata_value("country")

    @property
    def country_code(self):
        return self.get_metadata_value("country_code")

    def set_country(self, name=None, code=None, lang="en"):
        if name is None and code is None:
            return
        code = code.upper() if code is not None else code
        if name is None and code is not None:
            try:
                c = pycountry.countries.get(alpha2=code)
                name = c.name
            except:
                pass
        if name is not None and code is None:
            try:
                c = pycountry.countries.get(name=name)
                code = c.alpha2
            except:
                pass
        if name is not None:
            self.set_metadata_value("country", name, lang)
        if code is not None:
            self.set_metadata_value("country_code", code, lang)

    @property
    def continent(self):
        return self.get_metadata_value("continent")

    @property
    def continent_code(self):
        return self.get_metadata_value("continent_code")

    def set_continent(self, name=None, code=None, lang="en"):
        if name is None and code is None:
            return
        if name is not None:
            self.set_metadata_value("continent", name, lang)
        if code is not None:
            self.set_metadata_value("continent_code", code, lang)

    @property
    def language(self):
        return self.get_metadata_value("language")

    @property
    def language_code(self):
        return self.get_metadata_value("language_code")

    def add_language(self, name=None, code=None, lang="en"):
        if name is None and code is None:
            return
        if name is not None:
            existing = self.get_metadata_value("language", lang)
            if existing is None:
                self.set_metadata_value("language", [name], lang)
            else:
                if name not in existing:
                    existing.append(name)
                    self.set_metadata_value("language", existing, lang)
        if code is not None:
            existing = self.get_metadata_value("language_code", lang)
            if existing is None:
                self.set_metadata_value("language_code", [code], lang)
            else:
                if code not in existing:
                    existing.append(code)
                    self.set_metadata_value("language_code", existing, lang)

    @property
    def repository_type(self):
        return self.get_metadata_value("repository_type")

    def add_repository_type(self, val, lang="en"):
        existing = self.get_metadata_value("repository_type", lang)
        if existing is None:
            self.set_metadata_value("repository_type", [val], lang)
        else:
            if val not in existing:
                existing.append(val)
                self.set_metadata_value("repository_type", existing, lang)

    @property
    def software(self):
        sw = self.register.get("software", [])
        l = []
        for s in sw:
            l.append((s.get("name"), s.get("version"), s.get("url")))
        return l

    def add_software(self, name, version, url):
        if "register" not in self.raw:
            self.raw["register"] = {}
        if "software" not in self.raw["register"]:
            self.raw["register"]["software"] = []
        obj = {"name" :  name}
        if version is not None:
            obj["version"] = version
        if url is not None:
            obj["url"] = url
        self.raw["register"]["software"].append(obj)

    @property
    def organisation(self):
        return self.raw.get("register", {}).get("organisation", [])

    def add_organisation_object(self, org_obj):
        """
        org obj needs to conform to the correct structure.  Do we
        need to extend the api to build the object?  Will do so later
        if necessary
        """
        if "register" not in self.raw:
            self.raw["register"] = {}
        if "organisation" not in self.raw["register"]:
            self.raw["register"]["organisation"] = []
        self.raw["register"]["organisation"].append(org_obj)

    @property
    def contact(self):
        return self.raw.get("register", {}).get("contact", [])

    def add_contact_object(self, contact_obj):
        """
        org obj needs to conform to the correct structure.  Do we
        need to extend the api to build the object?  Will do so later
        if necessary
        """
        if "register" not in self.raw:
            self.raw["register"] = {}
        if "contact" not in self.raw["register"]:
            self.raw["register"]["contact"] = []
        self.raw["register"]["contact"].append(contact_obj)

    def add_api_object(self, api_obj):
        """
        api obj needs to conform to correct structure
        """
        # check that the api section of the object exists
        if "register" not in self.raw:
            self.raw["register"] = {}
        if "api" not in self.raw["register"]:
            self.raw["register"]["api"] = []

        # back out if we already have this url in the list
        for api in self.raw["register"]["api"]:
            if api.get("base_url") == api_obj.get("base_url"):
                return

        # if we get to here this is a new api object so we add it
        self.raw["register"]["api"].append(api_obj)

    def get_api(self, type=None):
        matches = []
        for api in self.raw.get("register", {}).get("api", []):
            if type is None:
                matches.append(api)
            else:
                if api.get("type") == type:
                    matches.append(api)
        return matches

    @property
    def created_date(self):
        return self.raw.get("created_date")
    
    def get_created_date(self, form):
        d = self.created_date
        if d:
            d = datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ")
        else:
            d = datetime.now()
        return datetime.strftime(d, form)

    @property
    def last_updated(self):
        return self.raw.get("last_updated")
    
    def get_last_updated(self, form):
        d = self.last_updated
        if d:
            d = datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ")
        else:
            d = datetime.now()
        return datetime.strftime(d, form)
    
    def get_metadata(self, lang):
        # FIXME: full implementation will be required for full multi-lingual support
        default = None
        for md in self.raw.get("register", {}).get("metadata", []):
            if md.get("lang") == lang:
                return deepcopy(md.get("record"))
            if md.get("default", False):
                default = md
        return deepcopy(default) # if we couldn't find the language you were looking for, return the default

    def get_metadata_value(self, key, lang=None):
        default_val = None

        # go through all the metadata records
        for md in self.raw.get("register", {}).get("metadata", []):

            # first get the value we are interested in
            rec = md.get("record")
            val = rec.get(key)

            # if we haven't been asked for a specific language, there is a value available, and this is the default
            # record, then return it
            if lang is None and md.get("default", False) and val is not None:
                return val

            # if we have been asked for a specific language, and this is it, and there is a value available,
            # then return it
            if lang is not None and lang == md.get("lang"):
                return val

            # finally, if we get here then we are after a value from a specific language, and this isn't the one
            # so just remember the default value in case we need to fall back on it later
            if md.get("default", False):
                default_val = val

        # by now we should either have returned, or picked up the default value.  If we are here, then just return
        # the default
        return default_val

    def set_metadata_value(self, key, value, lang=None):
        if lang is None:
            mdr = self.get_default_metadata()
        else:
            mdr = self.make_metadata(lang)
        mdr["record"][key] = value

    def get_default_metadata(self):
        for md in self.raw.get("register", {}).get("metadata", []):
            if md.get("default", False):
                return md
        return None

    def make_metadata(self, lang, default=False):
        # ensure the register and metadata locations exist
        if "register" not in self.raw:
            self.raw["register"] = {}
        if "metadata" not in self.raw.get("register"):
            self.raw["register"]["metadata"] = []

        # if this is the first metadata record, make it the default
        if len(self.raw.get("register", {}).get("metadata", [])) == 0:
            default = True

        # go through all the metadata records to see if we have one for this language
        for md in self.raw.get("register", {}).get("metadata", []):
            if md.get("lang") == lang:
                """
                FIXME: perhaps this is not the place to modify default status

                # if we do, normalise the default status(es)
                is_default = md.get("default", False)
                if is_default and default:
                    # it is the default, and we want it to be the default, so do nothing
                    pass
                elif is_default and not default:
                    # it is the default, and we want it to not be the default, we can't do it right now
                    raise OARRClientException("You must always have a default metadata record")
                elif not is_default and default:
                    # it isn't the default but we want it to be, so unset the old default and set the new one
                    current_default = self.get_default_metadata()
                    del current_default["default"]
                    md["default"] = True
                elif not is_default and not default:
                    # it's not the default and we don't want it to be, so do nothing
                    pass
                """
                return md

        # if we get to here there wasn't one for the requested language, so we make one
        md = {"lang" : lang, "default" : default, "record" : {}}
        if default:
            # unset the default status on the current default if necessary (note that this is ok, because
            # we are creating a new default, rather than re-assigning the default through this method)
            current_default = self.get_default_metadata()
            if current_default is not None:
                del current_default["default"]

        # store the metadata on the raw data and then return its handle
        self.raw["register"]["metadata"].append(md)
        return md


    def id_part(self, info_uri):
        if info_uri.startswith("info:oarr:"):
            return info_uri[10:]
        return info_uri
        
        
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
    


def _prep_record(record,request):
    if "register" not in record: record["register"] = {}
    if "metadata" not in record["register"]: record["register"]["metadata"] = []
    if "admin" not in record: record["admin"] = {}
    if "opendoar" not in record['admin']: record["admin"]["opendoar"] = {}

    if 'register__operational_status' in request.form:
        record['register']['operational_status'] = request.form['register__operational_status']

    if 'admin__opendoar__in_opendoar' in request.form.keys() and request.form['admin__opendoar__in_opendoar'] == "on":
        record['admin']['opendoar']['in_opendoar'] = True
    else:
        record['admin']['opendoar']['in_opendoar'] = False

    if 'admin__opendoar__updaterequest' in request.form.keys():
        if len(request.form['admin__opendoar__updaterequest']) > 0:
            record['admin']['opendoar']['updaterequest'] = request.form['admin__opendoar__updaterequest']
    elif record['admin']['opendoar'].get('updaterequest',False):
        del record['admin']['opendoar']['updaterequest']
        

    newmeta = []
    for k,v in enumerate(request.form.getlist('register__metadata__lang')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                lists = {
                    "register__metadata__record__language": [],
                    "register__metadata__record__repository_type": [],
                    "register__metadata__record__content_type": [],
                    "register__metadata__record__certification": [],
                    "register__metadata__record__subject__term": []
                }
                for n in lists.keys():
                    nk = request.form.getlist(n)[k]
                    if ',' in nk:
                        nklt = reader(StringIO.StringIO(nk))
                        nkl = nklt.next()
                    else:
                        nkl = [nk]
                    for vr in nkl:
                        val = vr.strip(" ")
                        if len(val) > 0: lists[n].append(val)
                try:
                    lc = []
                    for l in lists["register__metadata__record__language"]:
                        lc.append(pycountry.languages.get(name=l)).alpha2
                except:
                    lc = []
                co = request.form.getlist("register__metadata__record__country")[k]
                try:
                    cc = pycountry.countries.get(name=co).alpha2
                except:
                    cc = ""
                if request.form.getlist("register__metadata__default")[k] == "on":
                    df = True
                else:
                    df = False
                newmeta.append({
                    "lang": v,
                    "default": df,
                    "record": {
                        "url": request.form.getlist("register__metadata__record__url")[k],
                        "name": request.form.getlist("register__metadata__record__name")[k],
                        "acronym": request.form.getlist("register__metadata__record__acronym")[k],
                        "established_date": request.form.getlist("register__metadata__record__established_date")[k],
                        "twitter": request.form.getlist("register__metadata__record__twitter")[k],
                        "country": co,
                        "country_code": cc,
                        "continent": request.form.getlist("register__metadata__record__continent")[k],
                        "continent_code": request.form.getlist("register__metadata__record__continent_code")[k],
                        "description": request.form.getlist("register__metadata__record__description")[k],
                        "language": lists['register__metadata__record__language'],
                        "language_code": lc,
                        "repository_type": lists['register__metadata__record__repository_type'],
                        "content_type": lists['register__metadata__record__content_type'],
                        "certification": lists['register__metadata__record__certification']#, 
                        #"subject": lists['register__metadata__record__subject__term']
                    }
                })
            except:
                pass
    if len(newmeta) != 0:
        record["register"]["metadata"] = newmeta
    else:
        print newmeta


    record["register"]["organisation"] = []
    for k,v in enumerate(request.form.getlist('register__organisation__details__name')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                roles = []
                nk = request.form.getlist("register__organisation__role")[k]
                if ',' in nk:
                    nklt = reader(StringIO.StringIO(nk))
                    nkl = nklt.next()
                else:
                    nkl = [nk]
                for vr in nkl:
                    val = vr.strip(" ")
                    if len(val) > 0: roles.append(val)
                co = request.form.getlist("register__organisation__details__country")[k]
                try:
                    cc = pycountry.countries.get(name=co).alpha2
                except:
                    cc = ""
                record["register"]["organisation"].append({
                    "details": {
                        "name": v,
                        "acronym": request.form.getlist("register__organisation__details__acronym")[k],
                        "country": co,
                        "country": cc,
                        "lat": request.form.getlist("register__organisation__details__lat")[k],
                        "lon": request.form.getlist("register__organisation__details__lon")[k],
                        "url": request.form.getlist("register__organisation__details__url")[k],
                        "unit": util.dewindows(request.form.getlist("register__organisation__details__unit")[k]),
                        "unit_acronym": request.form.getlist("register__organisation__details__unit_acronym")[k],
                        "unit_url": request.form.getlist("register__organisation__details__unit_url")[k]
                    },
                    "role": roles
                })
            except:
                pass

    record["register"]["contact"] = []
    for k,v in enumerate(request.form.getlist('register__contact__details__email')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                roles = []
                nk = request.form.getlist("register__contact__role")[k]
                if ',' in nk:
                    nklt = reader(StringIO.StringIO(nk))
                    nkl = nklt.next()
                else:
                    nkl = [nk]
                for vr in nkl:
                    val = vr.strip(" ")
                    if len(val) > 0: roles.append(val)
                record["register"]["contact"].append({
                    "details": {
                        "email": v,
                        "name": request.form.getlist("register__contact__details__name")[k],
                        "job_title": request.form.getlist("register__contact__details__job_title")[k],
                        "phone": request.form.getlist("register__contact__details__phone")[k],
                        "fax": request.form.getlist("register__contact__details__fax")[k],
                        "address": request.form.getlist("register__contact__details__address")[k],
                        "lat": request.form.getlist("register__contact__details__lat")[k],
                        "lon": request.form.getlist("register__contact__details__lon")[k]
                    },
                    "role": roles
                })
            except:
                pass

    record["register"]["policy"] = []
    for k,v in enumerate(request.form.getlist('register__policy__policy_type')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                terms = []
                nk = request.form.getlist("register__policy_terms")[k]
                if ',' in nk:
                    nklt = reader(StringIO.StringIO(nk))
                    nkl = nklt.next()
                else:
                    nkl = [nk]
                for vr in nkl:
                    val = vr.strip(" ")
                    if len(val) > 0: terms.append(val)
                record["register"]["policy"].append({
                    "terms": terms,
                    "policy_type": v
                })
            except:
                pass

    newapilist = []
    if "api" not in record["register"]: record["register"]["api"] = []
    oldurllist = [i["base_url"] for i in record["register"]["api"]]
    for k,v in enumerate(request.form.getlist('register__api__base_url')):
        if v is not None and len(v) > 0 and v != " ":            
            try:
                if v in oldurllist:
                    newapilist.append(record["register"]["api"][oldurllist.index(v)])
                else:
                    record["register"]["api"].append({
                        "base_url": v,
                        "api_type": request.form.getlist("register__api__api_type")[k],
                    })
            except:
                pass
    record["register"]["api"] = newapilist

    record["register"]["software"] = []
    for k,v in enumerate(request.form.getlist('register__software__name')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                record["register"]["software"].append({
                    "name": v,
                    "version": request.form.getlist("register__software__version")[k],
                    "url": request.form.getlist("register__software__url")[k]
                })
            except:
                pass

    record["register"]["integration"] = []
    for k,v in enumerate(request.form.getlist('register__integration__integrated_with')):
        if v is not None and len(v) > 0 and v != " ":
            try:
                record["register"]["integration"].append({
                    "with": v,
                    "nature": request.form.getlist("register__integration__nature")[k],
                    "url": request.form.getlist("register__integration__url")[k],
                    "software": request.form.getlist("register__integration__software")[k],
                    "version": request.form.getlist("register__integration__version")[k],
                })
            except:
                pass

    return record


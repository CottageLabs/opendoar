from portality.autodiscovery import detectors
from portality import schema
from portality import oarr
import requests, logging, json, pycountry, urlparse, babel
from datetime import datetime
from incf.countryutils import transformations

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

class RegistryFileException(Exception):
    def __init__(self, message, errors, obj=None):
        self.message = message
        self.errors = errors
        self.obj = obj

    def obj_as_json(self):
        if self.obj is not None:
            return json.dumps(self.obj, indent=2)
        return None

class RegistryFile(object):

    _file_schema = {
        "fields" : ["last_updated"],
        "objects" : ["register"]
    }

    _register_schema = {
        "fields" : ["operational_status", "replaces"],
        "lists" : ["metadata", "software", "contact", "organisation", "policy", "api", "integration"],
        "list_entries" : {
            "metadata" : {
                "bools" : ["default"],
                "fields" : ["lang"],
                "objects" : ["record"],
                "object_entries" : {
                    "record" : {
                        "fields" : ["country_code", "twitter", "acronym", "description", "established_date", "name", "url"],
                        "lists" : ["language_code", "subject", "repository_type", "certification", "content_type"],
                        "list_entries" : {
                            "subject" : {
                                "fields" : ["scheme", "term", "code"]
                            }
                        }
                    }
                }
            },
            "software" : {
                "fields" : ["name", "version", "url"]
            },
            "contact" : {
                "lists" : ["role"],
                "objects" : ["details"],
                "object_entries" : {
                    "details" : {
                        "fields" : ["name", "email", "address", "fax", "phone", "lat", "lon", "job_title"]
                    }
                }
            },
            "organisation" : {
                "lists" : ["role"],
                "objects" : ["details"],
                "object_entries" : {
                    "details" : {
                        "fields" : ["name", "acronym", "url", "unit", "unit_acronym", "unit_url", "country_code", "lat", "lon"]
                    }
                }
            },
            "policy" : {
                "fields" : ["policy_type", "description"],
                "lists" : ["terms"]
            },
            "api" : {
                "fields" : ["api_type", "version", "base_url"],
                "bools" : ["authorisation"],
                "lists" : ["metadata_formats", "accepts", "accept_packaging"],
                "list_entries" : {
                    "metadata_formats" : {
                        "fields" : ["prefix", "namespace", "schema"]
                    }
                }
            },
            "integration" : {
                "fields" : ["integrated_with", "nature", "url", "software", "version"]
            }
        }
    }

    _operational_status = ["Trial", "Operational"]

    @classmethod
    def get(cls, repo_url):
        # first locate and retrieve the file
        resp = cls.autodetect(repo_url)
        if resp is None:
            log.info("Unable to locate OARR file for " + repo_url)
            return None
        log.info("Located OARR file for " + repo_url)

        # now do the validation
        obj = cls.validate(resp.text, repo_url)

        # if we have successfully validated, then make a new registry object and then expand
        # the data based on what we know
        reg = cls.expand(obj)
        return reg

    @classmethod
    def validate(cls, registry_file_content, source):
        # now attempt to parse the file contents as json
        try:
            obj = json.loads(registry_file_content)
        except ValueError:
            log.info("OARR file did not parse as JSON from " + source)
            raise RegistryFileException("error reading file", ["OARR file did not parse as JSON from " + source])

        # if we parsed it as json, next check that the shape of the file is right
        schema_valid, smessages = cls.schema_validate(obj)
        if not schema_valid:
            raise RegistryFileException("error validating file", smessages, obj)

        # if the schema was valid, go and check that it has all the correct content
        content_valid, cmessages = cls.content_validate(obj)
        if not content_valid:
            raise RegistryFileException("error validating file", cmessages, obj)

        return obj

    @classmethod
    def _localised_territory(cls, territory, lang):
        l = babel.Locale.parse("und_" + territory) # <- get a given country's locale with unknown language
        return l.get_territory_name(lang) # <- get the name of that country in a given language

    @classmethod
    def _localised_language(cls, language_code, lang):
        l = babel.Locale.parse(language_code)
        return l.get_language_name(lang)

    @classmethod
    def _continent(cls, country_code):
        continent_code = transformations.cca_to_ctca2(country_code)
        continent = transformations.cca_to_ctn(country_code)
        return continent_code, continent

    @classmethod
    def expand(cls, obj):
        r = obj.get("register", {})
        mds = r.get("metadata", [])

        for md in mds:
            record = md.get("record", {})

            # normalise metadata.lang -> lower case
            lang = md.get("lang", "en").lower()
            md["lang"] = lang

            cc = record.get("country_code")
            if cc is not None:
                # normalise metadata.record.country_code -> upper case
                cc = cc.upper()
                record["country_code"] = cc

                # set metadata.record.country from metadata.record.country_code in the correct language (metadata.lang)
                country = cls._localised_territory(cc, lang)
                record["country"] = country

                # set metadata.record.continent_code in all metadata.records
                # set metadata.record.continent for metadata.record.continent_code in the correct language (metadata.lang)
                # FIXME: we do not have translations of continent names, so they are always in english
                continent_code, continent = cls._continent(cc)
                record["continent_code"] = continent_code
                record["continent"] = continent

            langs = record.get("language_code", [])

            # normalise metadata.record.language_code -> lower case
            norm_langs = [l.lower() for l in langs]
            record["language_code"] = norm_langs

            # set metadata.record.language from metadata.record.language_code in the correct language (metadata.lang)
            full_lang_names = []
            for l in norm_langs:
                full_lang_names.append(cls._localised_language(l, lang))
            record["language"] = full_lang_names

        orgs = r.get("organisation", [])
        for org in orgs:
            details = org.get("details", {})
            cc = details.get("country_code")
            if cc is not None:
                # normalise organisation.details.country_code -> upper case
                cc = cc.upper()
                details["country_code"] = cc

                # set organisation.details.country from organisation.details.country_code in english
                country = cls._localised_territory(cc, "en")
                details["country"] = country

        # finally make a register object out of the raw object and return
        reg = oarr.Register(obj)
        return reg

    @classmethod
    def schema_validate(cls, obj):
        try:
            schema.validate(obj, cls._file_schema)
        except schema.ObjectSchemaValidationError as e:
            log.info("Could not validate the structure of the file: " + e.message)
            return False, [e.message]

        try:
            schema.validate(obj.get("register"), cls._register_schema)
        except schema.ObjectSchemaValidationError as e:
            log.info("Could not validate the structure of the file: " + e.message)
            return False, [e.message]

        return True, []

    @classmethod
    def content_validate(cls, obj):
        msgs = []

        # last_updated must be a timestamp of the form YYYY-mm-ddTHH:MM:SSZ
        lu = obj.get("last_updated")
        if lu is not None:
            try:
                datetime.strptime(lu, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                msg = "last updated date is not of the form YYYY-mm-ddTHH:MM:SSZ : " + str(lu)
                log.info(msg)
                msgs.append(msg)

        # there must be a register object, otherwise there's no point
        reg = obj.get("register")
        if reg is None or len(reg.keys()) == 0:
            msg = "No register object in the registry file"
            log.info(msg)
            msgs.append(msg)
            return False, msgs

        # "replaces" must take the form of an oarr info uri
        replaces = reg.get("replaces")
        if replaces is not None:
            if not replaces.startswith("info:oarr:"):
                msg = "identifier for object being replaced must take the form of the info uri (info:oarr:<identifier>) " + str(replaces)
                log.info(msg)
                msgs.append(msg)

        # "operational status" must be one of Trial or Operational
        opstat = reg.get("operational_status")
        if opstat is not None:
            if opstat not in cls._operational_status:
                msg = "operational_status must be one of " + str(cls._operational_status) + " but is " + str(opstat)
                log.info(msg)
                msgs.append(msg)

        # check that if there are multiple metadata records, they are in different languages and there is only
        # one default
        mds = reg.get("metadata", [])
        langs = []
        default = False
        for md in mds:
            lang = md.get("lang")
            if lang is None:
                msg = "lang for metadata record must be set"
                log.info(msg)
                msgs.append(msg)
            else:
                if lang in langs:
                    msg = "lang " + str(lang) + " is repeated in list of metadata records"
                    log.info(msg)
                    msgs.append(msg)
                else:
                    langs.append(lang)

            d = md.get("default", False)
            if d and default:
                msg = "Two or more metadata records are marked as default"
                log.info(msg)
                msgs.append(msg)
            elif d:
                default = True
        if not default and len(mds) > 0:
            msg = "There is no metadata record which is marked as the default"
            log.info(msg)
            msgs.append(msg)

        # check the structure of each metadata record
        for md in mds:
            # ensure that the language is iso-639-1
            lang = md.get("lang")
            if lang is not None:
                try:
                    pylan = pycountry.languages.get(alpha2=lang.lower())
                except KeyError:
                    msg = "metadata record language " + str(lang) + " is not recognised as an iso-639-1 language code"
                    log.info(msg)
                    msgs.append(msg)

            # ensure there is a metadata record and that it has values in it
            record = md.get("record")
            if record is None or len(record.keys()) == 0:
                msg = "No record entry in the metadata object, or record entry is empty"
                log.info(msg)
                msgs.append(msg)
                continue

            # ensure the country code is iso-3166-1
            cc = record.get("country_code")
            if cc is not None:
                try:
                    pyc = pycountry.countries.get(alpha2=cc.upper())
                except KeyError:
                    msg = "country code " + str(cc) + " is not recognised as an iso-3166-1 country code"
                    log.info(msg)
                    msgs.append(msg)

            # ensure the established date is a 4 digit number less than today's date and more recent than some
            # reasonable time in the past
            ed = record.get("established_date")
            if ed is not None:
                now = datetime.now().year
                try:
                    ed = int(ed)
                    if ed >= now:
                        msg = "established date " + str(ed) + " is in the future"
                        log.info(msg)
                        msgs.append(msg)
                    elif ed <= 1970: # arbitrary date in the past before which there were no digital repositories
                        msg = "established date " + str(ed) + " is too far in the past"
                        log.info(msg)
                        msgs.append(msg)
                except ValueError:
                    msg = "established date " + str(ed) + " is not a number; should be a 4 digit year"
                    log.info(msg)
                    msgs.append(msg)

            # ensure all the language codes are iso-639-1
            lcs = record.get("language_code", [])
            for lc in lcs:
                try:
                    pylan = pycountry.languages.get(alpha2=lang.lower())
                except KeyError:
                    msg = "content language " + str(lc) + " is not recognised as an iso-639-1 language code"
                    log.info(msg)
                    msgs.append(msg)

            # ensure that the url looks realistic (only a basic attempt, don't try too hard)
            url = record.get("url")
            if url is not None:
                cls._validate_url(url, msgs)
            default = md.get("default", False)
            if default and url is None:
                msg = "default metadata record does not contain the repository url"
                log.info(msg)
                msgs.append(msg)

        # check the structure of each software entry
        softwares = reg.get("software", [])
        for software in softwares:
            name = software.get("name")
            if name is None or name == "":
                msg = "the name of the software is not present"
                log.info(msg)
                msgs.append(msg)
            url = software.get("url")
            if url is not None:
                cls._validate_url(url, msgs)

        # check the structure of each contact
        contacts = reg.get("contact", [])
        for contact in contacts:
            details = contact.get("details")
            if details is None or len(details.keys()) == 0:
                msg = "contact does not contain a details object, or details object is empty"
                log.info(msg)
                msgs.append(msg)
                continue

            lat = details.get("lat")
            lon = details.get("lon")
            if (lat is not None and lon is None) or (lat is None and lon is not None):
                msg = "contact's latitude and longitude must both be specified"
                log.info(msg)
                msgs.append(msg)
            elif lat is not None and lon is not None:
                try:
                    float(lat)
                    if lat > 90.0 or lat < -90.0:
                        msg = "contact's latitude is outside the allowable range (-90 -> 90): " + str(lat)
                        log.info(msg)
                        msgs.append(msg)
                except ValueError:
                    msg = "contact's latitude is not numeric: " + str(lat)
                    log.info(msg)
                    msgs.append(msg)

                try:
                    float(lon)
                    if lon > 180.0 or lon < -180.0:
                        msg = "contact's longitude is outside the allowable range (-180 -> 180): " + str(lon)
                        log.info(msg)
                        msgs.append(msg)
                except ValueError:
                    msg = "contact's longitude is not numeric: " + str(lon)
                    log.info(msg)
                    msgs.append(msg)

        # check the structure of each organisation
        orgs = reg.get("organisation", [])
        for org in orgs:
            details = org.get("details")
            if details is None or len(details.keys()) == 0:
                msg = "organisation does not contain a details object or details object is empty"
                log.info(msg)
                msgs.append(msg)
                continue

            url = details.get("url")
            if url is not None:
                cls._validate_url(url, msgs)

            unit_url = details.get("unit_url")
            if unit_url is not None:
                cls._validate_url(unit_url, msgs)

            cc = details.get("country_code")
            if cc is not None:
                try:
                    pyc = pycountry.countries.get(alpha2=cc.upper())
                except KeyError:
                    msg = "in organisation, country code " + str(cc) + " is not recognised as an iso-3166-1 country code"
                    log.info(msg)
                    msgs.append(msg)

            lat = details.get("lat")
            lon = details.get("lon")
            if (lat is not None and lon is None) or (lat is None and lon is not None):
                msg = "organisation's latitude and longitude must both be specified"
                log.info(msg)
                msgs.append(msg)
            elif lat is not None and lon is not None:
                try:
                    float(lat)
                    if lat > 90.0 or lat < -90.0:
                        msg = "organisation's latitude is outside the allowable range (-90 -> 90): " + str(lat)
                        log.info(msg)
                        msgs.append(msg)
                except ValueError:
                    msg = "organisation's latitude is not numeric: " + str(lat)
                    log.info(msg)
                    msgs.append(msg)
                try:
                    float(lon)
                    if lon > 180.0 or lon < -180.0:
                        msg = "organisation's longitude is outside the allowable range (-180 -> 180): " + str(lon)
                        log.info(msg)
                        msgs.append(msg)
                except ValueError:
                    msg = "organisation's longitude is not numeric: " + str(lon)
                    log.info(msg)
                    msgs.append(msg)

        # check the policies
        policies = reg.get("policy", [])
        for policy in policies:
            terms = policy.get("terms", [])
            if len(terms) == 0:
                msg = "policy must contain one or more policy terms"
                log.info(msg)
                msgs.append(msg)
            pt = policy.get("policy_type")
            if pt is None:
                msg = "policy must specify a policy type"
                log.info(msg)
                msgs.append(msg)

        # check the apis
        apis = reg.get("api", [])
        for api in apis:
            apitype = api.get("api_type")
            if apitype is None:
                msg = "api entry must specify a type"
                log.info(msg)
                msgs.append(msg)
            url = api.get("base_url")
            if url is None:
                msg = "api entry must specify a base url"
                log.info(msg)
                msgs.append(msg)
            else:
                cls._validate_url(url, msgs)

            mfs = api.get("metadata_formats", [])
            if apitype == "oai-pmh":
                for mf in mfs:
                    prefix = mf.get("prefix")
                    if prefix is None:
                        msg = "metadata_format must contain the prefix"
                        log.info(msg)
                        msgs.append(msg)
            else:
                if len(mfs) > 0:
                    msg = "metadata_format can only be present for apis of type oai-pmh"
                    log.info(msg)
                    msgs.append(msg)

            accepts = api.get("accepts", [])
            accept_packaging = api.get("accept_packaging", [])
            if apitype != "sword" and len(accepts) > 0:
                msg = "accepts can only be present for apis of type sword"
                log.info(msg)
                msgs.append(msg)
            if apitype != "sword" and len(accept_packaging) > 0:
                msg = "accept_packaging can only be present for apis of type sword"
                log.info(msg)
                msgs.append(msg)

        # check the integration
        integrations = reg.get("integration", [])
        for integration in integrations:
            iw = integration.get("integrated_with")
            if iw is None:
                msg = "integration section must specify integrated_with"
                log.info(msg)
                msgs.append(msg)
            url = integration.get("url")
            if url is not None:
                cls._validate_url(url, msgs)

        return len(msgs) == 0, msgs

    @classmethod
    def autodetect(cls, repo_url):
        info = detectors.Info()
        href = None

        # check for auto-discovery headers
        soup = info.soup(repo_url)
        if soup is not None:
            for link in soup.find_all("link"):
                if "oarr" in link.get("rel"):
                    href = cls._expand_url(repo_url, link.get("href"))
                    break

        if href is not None:
            resp = cls.retrieve(href)
            if resp is not None:
                return resp

        # if we didn't find the headers, then try the default location
        href = cls._expand_url(repo_url, "/oarr.json")
        resp = cls.retrieve(href)
        if resp is not None:
            return resp

        # couldn't find the file, or there was an error
        return None

    @classmethod
    def retrieve(cls, registry_file_url):
        resp = requests.get(registry_file_url)
        if resp.status_code == requests.codes.ok:
            return resp
        return None

    @classmethod
    def _validate_url(cls, url, msgs):
        parsed = None
        try:
            parsed = urlparse.urlparse(url)
        except:
            msg = "unable to parse url: " + str(url)
            log.info(msg)
            msgs.append(msg)
        if parsed is None:
            return
        if parsed.scheme == "":
            msg = "url does not contain a scheme (e.g. http or https): " + str(url)
            log.info(msg)
            msgs.append(msg)
        if "." not in parsed.netloc:
            msg = "url domain does not look complete " + str(url)
            log.info(msg)
            msgs.append(msg)

    @classmethod
    def _expand_url(cls, origin_url, rel):
        if rel.startswith("http://") or rel.startswith("https://"):
            return rel

        parsed = urlparse.urlparse(origin_url)

        if rel.startswith("/"):
            # absolute to the base of the domain
            return parsed.scheme + "://" + parsed.netloc + rel
        else:
            full = parsed.scheme + "://" + parsed.netloc + parsed.path
            if full.endswith("/"):
                return full + rel
            else:
                parts = full.split("/")
                if len(parts) == 3:
                    return full + "/" + rel
                elif len(parts) > 3:
                    return "/".join(full[:-1]) + "/" + rel

        return None
import requests, re, logging, socket, pycountry, os
from incf.countryutils import transformations
from urlparse import urlparse
from babel import Locale
from lxml import etree


# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

class Detector(object):
    def name(self):
        return "Abstract Detector"
    def detectable(self, register):
        return False
    def detect(self, register, info):
        pass

class OperationalStatus(Detector):
    """Attempts to determine if the repository is operational"""

    ip_rx = "(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"

    def name(self):
        return "Operational Status"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        """
        Operational - has readable url with no port number and responds to get
        Trial - has url with ip and/or port number and responds to get
        Broken - does not respond to get or responds with an error code
        """
        url = register.repo_url

        try:
            log.info("Requesting repository home page from " + url)
            resp = requests.get(url, timeout=5)
            info["url_get"] = resp
        except:
            log.info("Repository did not respond - registering operational_status as Broken")
            register.operational_status = "Broken"
            return

        if resp.status_code != requests.codes.ok:
            log.info("Repository responded with error - registering operational_status as Broken")
            register.operational_status = "Broken"
            return

        pn = self._has_port_number(url)
        ip = self._is_ip(url)

        if pn or ip:
            log.info("Repository is by IP address and/or has port number - registering operational_status as Trial")
            register.operational_status = "Trial"

        # operation status is Operational
        log.info("Repository is responding appropriately - registering operational_status as Operational")
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

class Country(Detector):
    hostip_api = "http://api.hostip.info/get_json.php"

    tld_map = {
        "uk" : "gb", # uk tld refers to gb in iso 3166-1
        "edu" : "us", # edu is almost completely us based
        "tp" : "tl" # old and new tlds for Timor
    }

    ignore_tld = ["eu"]

    def name(self):
        return "Country"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # our first best bet is to get the cctld off the url
        url = register.repo_url
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0] # ensure we get rid of the port
        tld = host.split(".")[-1] # the final part of the domain

        # map the tld to the iso 3166-1 form if necessary
        tld = self.tld_map.get(tld.lower(), tld)

        try:
            c = pycountry.countries.get(alpha2=tld.upper())
            log.info("Detecting country based on TLD: " + tld + " -> " + c.name)
            register.set_country(name=c.name, code=c.alpha2)
            return
        except KeyError:
            log.info("TLD did not map to a known country: " + tld)
            pass

        # if we get down to here we have to try and geolocate the ip
        ip = socket.gethostbyname(parsed.netloc)
        r = self.hostip_api + "?ip=" + ip
        log.info("GeoLocating IP using: " + r)

        resp = requests.get(r)
        j = resp.json()
        code = j.get("country_code")
        try:
            c = pycountry.countries.get(alpha2=code.upper())
            log.info("GeoLocated country from IP: " + ip + " -> " + c.name)
            register.set_country(name=c.name, code=c.alpha2)
            return
        except KeyError:
            pass

        log.info("Unable to determine country for " + url)

class Continent(Detector):
    def name(self):
        return "Continent"

    def detectable(self, register):
        return register.country_code is not None

    def detect(self, register, info):
        code = register.country_code
        continent_code = transformations.cca_to_ctca2(code)
        continent = transformations.cca_to_ctn(code)
        register.set_continent(name=continent, code=continent_code)
        log.info("Determined continent from country: " + code + " -> " + continent)

class Language(Detector):
    def name(self):
        return "Language"

    def detectable(self, register):
        return register.repo_url is not None or register.country_code is not None

    def detect(self, register, info):
        # first thing is to check the http headers for a content-language
        resp = info.get("url_get")
        if resp is None and register.repo_url is not None:
            resp = requests.get(register.repo_url)
            info["url_get"] = resp
        if resp is not None:
            lang = resp.headers.get("content-language")
            keep_trying = False

            # if we find a language, try to normalise to to digits and then identify it
            if lang is not None:
                lang, territory = self._parse(lang)
                log.info("Determining language based on HTTP headers " + register.repo_url + " -> " + lang + ", " + territory)
                try:
                    locale = Locale(lang.lower(), territory.upper())
                    register.add_language(name=locale.language_name, code=locale.language)
                except KeyError:
                    log.info("Unable to find Locale for " + lang + ", " + territory)
                    keep_trying = True

                # if we got the language from the headers we are done
                if not keep_trying:
                    return

        # we can infer the language from the country
        if register.country_code is not None:
            try:
                langs = self._get_territory_languages(register.country_code)
                log.info("Determining language based on territory " + register.country_code + " -> " + str(langs))
                for lang in langs:
                    locale = Locale(lang.lower())
                    register.add_language(name=locale.language_name, code=locale.language)
            except KeyError:
                log.info("Unable to find Locale for one or more of " + str(langs))

    def _parse(self, lang):
        if len(lang) == 5:
            sep = None
            if "-" in lang:
                sep = "-"
            elif "_" in lang:
                sep = "_"
            bits = lang.split(sep)
            if len(bits) == 2:
                return tuple(bits)
            elif len(bits) > 2:
                return bits[0], bits[1]
            elif len(bits) == 1:
                return bits[0], None

        if len(lang) == 2:
            return lang, None

        return lang, None

    def _get_territory_languages(self, territory):
        thisdir = os.path.dirname(os.path.realpath(__file__))
        sd = os.path.join(thisdir, "supplementalData.xml")
        langtree = etree.parse(open(sd))

        try:
            ti = langtree.xpath("territoryInfo/territory[@type='" + territory.upper() + "']")[0]
        except IndexError:
            return None

        lps = ti.findall("languagePopulation")

        # if there is only one language, it is the one
        if len(lps) == 1:
            return [lps[0].get("type")]

        territory_languages = []
        for lp in lps:
            if lp.get("officialStatus") == "official":
                territory_languages.append(lp.get("type"))

        return list(set(territory_languages))


#############################################################
# List of detectors and the order they should run
#############################################################

GENERAL = [
    OperationalStatus,
    Country,
    Continent,
    Language
]
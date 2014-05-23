import requests, re, logging, socket, pycountry, os
from incf.countryutils import transformations
from urlparse import urlparse
from babel import Locale
from lxml import etree
from bs4 import BeautifulSoup
import rdflib
import whois


# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

################################################################
## utilities

class WhoIsWrapper(object):

    fields = {
        "org_name" : ["Registrant Organization", "Admin Organization", "Registered For", "Domain Owner", "Tech Organization", "Registered By"],
        "domain" : ["Domain", "Domain Name"],
        "registrant_address" : ["Registrant Address"]
    }

    long_pattern = ":\n\t(.+?)\n\n"
    short_pattern = ":(.+?)\n"

    def __init__(self, host):
        self.who = whois.whois(host)
        if self.who:
            self.body = self.who.text
        else:
            self.body = ""

    def get(self, field):
        synonyms = self.fields.get(field, [])
        for syn in synonyms:
            p = syn + self.long_pattern
            m = re.search(p, self.body)
            if m is not None:
                return m.group(1)
            p = syn + self.short_pattern
            m = re.search(p, self.body)
            if m is not None:
                return m.group(1)
        return None


###############################################################
## Infrastructure classes for detection

class Info(object):
    def __init__(self):
        self.cache = {}

    def get(self, cached, default=None):
        return self.cache.get(cached, default)

    def set(self, key, obj):
        self.cache[key] = obj

    def url_get(self, url):
        try:
            # have we already tried and found the url timed out?
            if self.get("timeout_" + url, False):
                return None

            # have we already tried and successfully received a response
            if self.get(url) is not None:
                return self.get(url)

            # if not, try, get a response and cache then return
            resp = requests.get(url, timeout=5)
            self.set(url, resp)
            return resp

        except requests.exceptions.ConnectionError:
            self.set("timeout_" + url, True)
        except requests.exceptions.Timeout:
            self.set("timeout_" + url, True)

    def soup(self, url):
        s = self.get("soup_" + url)
        if s is not None:
            return s
        resp = self.url_get(url)
        if resp is None:
            return None
        s = BeautifulSoup(resp.text)
        self.set("soup_" + url, s)
        return s

    def graph(self, url, mimetype=None):
        g = self.get("graph_" + url)
        if g is not None:
            return g
        if not mimetype:
            mimetype = rdflib.util.guess_format(url)
        if mimetype is None:
            return
        resp = self.url_get(url)
        if resp is None:
            return None
        g = rdflib.Graph()
        g.parse(format=mimetype, data=resp.text)
        self.set("graph_" + url, g)
        return g

    def whois(self, host):
        who = self.get("whois_" + host)
        if who is not None:
            return who
        who = WhoIsWrapper(host)
        self.set("whois_" + host, who)
        return who

class Detector(object):
    def name(self):
        return "Abstract Detector"
    def detectable(self, register):
        return False
    def detect(self, register, info):
        pass

################################################################
## Detector implementations

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

        log.info("Requesting repository home page from " + url)
        resp = info.url_get(url)
        if resp is None:
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

        resp = info.url_get(r)
        if resp is None:
            return

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
        # get the repo page (from cache or from the url)
        resp = info.url_get(register.repo_url)

        # first thing is to check the http headers for a content-language
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

class RepositoryType(Detector):
    # Some weak attempts to differentiate between the different types of repo based on their url suffix
    # At best is indicative.
    institutional_suffix = [
        ".ac.uk", ".edu"
    ]
    institutional_substring = [
        ".edu."
    ]

    governmental_suffix = [
        ".gov.uk", ".gov"
    ]
    governmental_substring = [
        ".gov."
    ]

    aggregating_suffix = [
        ".org", ".com", ".info", ".net"
    ]

    disciplinary_suffix = [
        ".org", ".com", ".info", ".net"
    ]

    def name(self):
        return "Repository Type"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        url = register.repo_url
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0] # ensure we get rid of the port

        for suffix in self.institutional_suffix:
            if host.endswith(suffix):
                register.add_repository_type("Institutional")
                log.info("Repository URL ends with " + suffix + ", assuming Institutional")
        for sub in self.institutional_substring:
            if sub in host:
                register.add_repository_type("Institutional")
                log.info("Repository URL contains " + sub + ", assuming Institutional")

        for suffix in self.governmental_suffix:
            if host.endswith(suffix):
                register.add_repository_type("Governmental")
                log.info("Repository URL ends with " + suffix + ", assuming Governmental")
        for sub in self.governmental_substring:
            if sub in host:
                register.add_repository_type("Governmental")
                log.info("Repository URL contains " + sub + ", assuming Governmental")

        for suffix in self.aggregating_suffix:
            if host.endswith(suffix):
                register.add_repository_type("Aggregating")
                log.info("Repository URL ends with " + suffix + ", assuming Aggregating")

        for suffix in self.disciplinary_suffix:
            if host.endswith(suffix):
                register.add_repository_type("Disciplinary")
                log.info("Repository URL ends with " + suffix + ", assuming Disciplinary")

        if register.repository_type is None or len(register.repository_type) == 0:
            register.add_repository_type("Institutional")
            log.info("Unable to guess Repository Type, so falling back to Institutional")

class Software(Detector):
    immediate_accept_threshold = 0.8
    acceptable_threshold = 0.5

    def name(self):
        return "Software"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # define the order we will run our identify functions in
        stack = [self.is_dspace, self.is_eprints]
        options = []

        # for each identify function, run it, then check to see if it has identified the software with
        # sufficient confidence.  If so, record and return.  If not, add it to the list of options, and
        # carry on
        for f in stack:
            software = f(register, info)
            if software is not None:
                if software.get("confidence", 0) >= self.immediate_accept_threshold:
                    self._record(register, info, software)
                    info.set("software_confidence", software.get("confidence", 0))
                    return
                else:
                    options.append(software)

        if len(options) == 0:
            return
        if len(options) == 1:
            if options[0].get("confidence", 0) > self.acceptable_threshold:
                self._record(register, info, options[0])
                info.set("software_confidence", software.get("confidence", 0))
                return

        best = None
        for o in options:
            if best is None:
                best = o
                continue
            if o.get("confidence", 0) > best.get("confidence", 0):
                best = o
        if best is not None:
            if best.get("confidence", 0) > self.acceptable_threshold:
                self._record(register, info, options[0])
                info.set("software_confidence", software.get("confidence", 0))


    def _record(self, register, info, software):
        register.add_software(software["name"], software["version"], software["url"])
        v = software.get("version")
        if v is None:
            v = "(no version)"
        log.info("Repository is identified as " + software["name"] + " " + v + " with confidence " + str(software.get("confidence")))

    def is_dspace(self, register, info):
        # get the repo page (from cache or from the url)
        resp = info.url_get(register.repo_url)

        # get the beautifulsoup of the home page
        soup = info.soup(register.repo_url)

        # template object that we will return upon success
        software = {"name" : "DSpace", "version": None, "url" : "http://dspace.org", "confidence" : 0}

        # may have <meta name="Generator" content="DSpace 3.1" /> in the html headers (has the version back to ~1.8)
        if soup is not None:
            for meta in soup.find_all("meta"):
                if meta.get("name") == "Generator":
                    content = meta.get("content")
                    if content is not None and content.strip().startswith("DSpace"):
                        software["confidence"] = 1.0
                        parts = content.strip().split(" ")
                        if len(parts) == 2:
                            software["version"] = parts[1]
                        return software

        # embedded opensearch link title may be "DSpace"
        if soup is not None:
            for link in soup.find_all("link"):
                if link.get("type") == "application/opensearchdescription+xml":
                    if link.get("title") == "DSpace":
                        software["confidence"] = 1.0
                        return software

        # may contain <a href="/dspace/help/index.html" target="dspacepopup">Help</a> somewhere
        if resp is not None:
            if 'target="dspacepopup">Help' in resp.text:
                software["confidence"] = 1.0
                return software

        # may have "dspace" in the URL
        if "dspace" in register.repo_url.lower():
            software["confidence"] = 0.9
            return software

        # may have "jspui" or "xmlui" in the url
        if "jspui" in register.repo_url.lower():
            software["confidence"] = 0.9
            return software
        if "xmlui" in register.repo_url.lower():
            software["confidence"] = 0.9
            return software

        # may contain the phrase "Communities & Collections" on the home page
        if "Communities & Collections" in soup.get_text():
            software["confidence"] = 0.8
            return software

        # May contain the word DSpace in a heading tag somewhere
        if resp is not None:
            if "dspace" in resp.text or "DSpace" in resp.text:
                software["confidence"] = 0.5
                return software

        return None

    def is_eprints(self, register, info):
        # get the repo page (from cache or from the url)
        resp = info.url_get(register.repo_url)

        # get the beautifulsoup of the home page
        soup = info.soup(register.repo_url)

        # template object that we will return upon success
        software = {"name" : "EPrints", "version": None, "url" : "http://eprints.org", "confidence" : 0}

        # may have <meta name="Generator" content="EPrints 3.3.11" /> in the html headers
        if soup is not None:
            for meta in soup.find_all("meta"):
                if meta.get("name") == "Generator":
                    content = meta.get("content")
                    if content is not None and content.strip().startswith("EPrints"):
                        software["confidence"] = 1.0
                        parts = content.strip().split(" ")
                        if len(parts) == 2:
                            software["version"] = parts[1]
                        return software

        # may have repository summary link in RDF which will contain the eprints version in rdfs:comment
        if soup is not None:
            for link in soup.find_all("link"):
                if link.get("title", "").startswith("Repository Summary"):
                    software["confidence"] = 1.0
                    log.info("Checking EPrints RDF file at " + link.get("href"))
                    g = info.graph(link.get("href"), link.get("type"))
                    self._eprints_extract_from_rdf(g, software)
                    return software

        # some or all of the following:
        # powered by <em><a href="http://eprints.org/software/">EPrints 3</a></em>
        # which is developed by the <a href="http://www.ecs.soton.ac.uk/">School of Electronics and Computer Science</a>
        # at the University of Southampton. <a href="http://aquaticcommons.org/eprints/">More information and software credits</a>.

        if resp is not None:
            if 'powered by <em><a href="http://eprints.org/software/">EPrints 3</a></em>' in resp.text:
                software["confidence"] = 1.0
                software["version"] = "3"
                return software
            if 'developed by the <a href="http://www.ecs.soton.ac.uk/">School of Electronics and Computer Science</a>' in resp.text:
                software["confidence"] = 0.8
                return software

        # may have eprints or e-prints in the url
        if "eprints" in register.repo_url.lower() or "e-prints" in register.repo_url.lower():
            software["confidence"] = 0.5
            return software

        return None

    def _eprints_extract_from_rdf(self, g, software):
        # one of the comments contains some useful info about the eprints version
        useful = None
        for s,o,p in g.triples((None, rdflib.URIRef("http://www.w3.org/2000/01/rdf-schema#comment"), None)):
            if p.startswith("This system is running eprints server software"):
                useful = p
                break

        if useful is not None:
            pattern = "\(EPrints (.+?) "
            m = re.search(pattern, useful)
            if m is not None:
                version = m.group(1)
                software["version"] = version

class Organisation(Detector):
    def name(self):
        return "Organisation"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # extract the host name from the url
        url = register.repo_url
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0] # ensure we get rid of the port

        # do the lookup.  This helpfully recurses up the domain tree until it
        # gets an answer
        who = info.whois(host)

        # try to extract the org details from the whois record
        address = who.get("org_address")
        name = who.get("org_name")
        domain = who.get("domain")

        # did we get anything we could work with?
        if address is None and name is None and domain is None:
            return

        # if so, start building an org object
        org = {"role" : ["host"], "details" : {}}
        if name is not None:
            org["details"]["name"] = name
            log.info("Detected name " + name + " from whois record")
        if domain is not None:
            org["details"]["url"] = "http://" + domain
            log.info("Detected domain " + domain + " from whois record")

        # FIXME: we have not extracted the address yet or done any geolocation on it
        # to do this will require quite a bit more work, so priority needs to be chosen

        register.add_organisation_object(org)

class Feed(Detector):
    def name(self):
        return "Atom/RSS Feeds"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        pass

#############################################################
# List of detectors and the order they should run
#############################################################

GENERAL = [
    OperationalStatus,
    Country,
    Continent,
    Language,
    RepositoryType,
    Software,
    Organisation,
    Feed
]
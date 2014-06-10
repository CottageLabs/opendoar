import requests, re, logging, socket, pycountry, os
from incf.countryutils import transformations
from urlparse import urlparse
from babel import Locale
from lxml import etree
from bs4 import BeautifulSoup
import rdflib
import whois
import feedparser
from io import BytesIO

# FIXME: this should probably come from configuration somewhere
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

################################################################
## utilities

class WhoIsWrapper(object):
    """
Registrant Phone:+49.17012345678
Registrant Phone Ext:
Registrant Fax:
Registrant Fax Ext:
Registrant Email:jung.uwe@gmail.com
"""

    fields = {
        "org_name" : ["Registrant Organization", "Admin Organization", "Registered For", "Domain Owner", "Tech Organization", "Registered By"],
        "domain" : ["Domain", "Domain Name"],
        "address" : ["Registrant Address",
                     ["Registrant Street", "Registrant City", "Registrant State/Province", "Registrant Postal Code", "Registrant Country"]
        ],
        "contact_name" : ["Registrant Name", "Registrant Contact", "Admin Name", "Tech Name"],
        "email" : ["Registrant Email", "Admin Email", "Tech Email"],
        "fax" : ["Registrant Fax", "Admin Fax", "Tech Fax"],
        "phone" : ["Registrant Phone", "Admin Phone", "Tech Phone"],
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
            if isinstance(syn, list):
                val = ""
                for s in syn:
                    raw = self.get_raw(s)
                    if raw is not None:
                        val += raw + "\n"
                if val != "":
                    return val.strip()
            else:
                val = self.get_raw(syn)
                if val is not None:
                    return val
        return None

    def get_raw(self, key):
        p = key + self.long_pattern
        m = re.search(p, self.body, re.DOTALL)
        if m is not None:
            return m.group(1)
        p = key + self.short_pattern
        m = re.search(p, self.body)
        if m is not None:
            return m.group(1)
        return None


###############################################################
## Infrastructure classes for detection

class Info(object):
    request_timeout = 10
    accept_language = "en"

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
            # note that we're ignoring any ssl errors here
            headers = {"Accept-Language" : self.accept_language}
            resp = requests.get(url, timeout=self.request_timeout, verify=False, headers=headers)
            self.set(url, resp)
            return resp

        except requests.exceptions.ConnectionError:
            self.set("timeout_" + url, True)
            return None
        except requests.exceptions.Timeout:
            self.set("timeout_" + url, True)
            return None

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

    def feed(self, url):
        f = self.get("feed_" + url)
        if f is not None:
            return f
        resp = self.url_get(url)
        if resp is None:
            return None
        f = feedparser.parse(resp.text)
        self.set("feed_" + url, f)
        return f

    def xml(self, url):
        x = self.get("xml_" + url)
        if x is not None:
            return x
        resp = self.url_get(url)
        if resp is None:
            return None
        try:
            x = etree.parse(BytesIO(bytearray(resp.text, "utf-8")))
        except:
            return None
        self.set("xml_" + url, x)
        return x

class Detector(object):
    def name(self):
        return "Abstract Detector"
    def detectable(self, register):
        return False
    def detect(self, register, info):
        pass

    def _expand_url(self, origin_url, rel):
        if rel.startswith("http://") or rel.startswith("https://"):
            return rel

        parsed = urlparse(origin_url)

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

class DetectorException(Exception):
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
            return

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
                log.info("Determining language based on HTTP headers " + register.repo_url + " -> " + lang + ", " + str(territory))
                try:
                    if territory is not None:
                        locale = Locale(lang.lower(), territory.upper())
                    else:
                        locale = Locale(lang.lower())
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
        if soup is not None:
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
        name = who.get("org_name")
        domain = who.get("domain")

        # did we get anything we could work with?
        if name is None and domain is None:
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

    type_map = {
        "application/rss+xml" : "rss",
        "application/atom+xml" : "atom"
    }

    version_map = {
        "rss090" : "0.90",
        "rss091n" : "Netscape 0.91",
        "rss091u" : "Userland 0.91",
        "rss10" : "1.0",
        "rss092" : "0.92",
        "rss093" : "0.93",
        "rss094" : "0.94",
        "rss20" : "2.0",
        "rss" : None,
        "atom01" : "0.1",
        "atom02" : "0.2",
        "atom03" : "0.3",
        "atom10" : "1.0",
        "atom" : None
    }

    def name(self):
        return "Atom/RSS Feeds"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        soup = info.soup(register.repo_url)
        if soup is None:
            return

        # look in the link headers in the html
        # <link type="application/rss+xml" rel="alternate" href="/feed/rss_1.0/site" />
        # <link type="application/rss+xml" rel="alternate" href="/feed/rss_2.0/site" />
        # <link type="application/atom+xml" rel="alternate" href="/feed/atom_1.0/site" />
        alts = []
        for link in soup.find_all("link"):
            rels = link.get("rel")
            if rels is None:
                continue
            if "alternate" in rels:
                if link.get("type") is not None and link.get("type") in ["application/rss+xml", "application/atom+xml"]:
                    url = self._expand_url(register.repo_url, link.get("href"))
                    if url is not None:
                        alts.append((url, link.get("type")))

        for url, mime in alts:
            feed = info.feed(url)
            api = {"api_type" : self.type_map.get(mime), "base_url" :  url}

            if feed.bozo == 0:
                v = self.version_map.get(feed.version)
                if v is not None:
                    api["version"] = v

            log.info(api.get("api_type") + " at " + api.get("base_url") + " detected from link headers")
            register.add_api_object(api)

        # anchor tags with RSS/Atom in the link body
        # <a href="/feed/rss_1.0/site" style="background: url(/static/icons/feed.png) no-repeat">RSS 1.0</a>
        # <a href="/feed/rss_2.0/site" style="background: url(/static/icons/feed.png) no-repeat">RSS 2.0</a>
        # <a href="/feed/atom_1.0/site" style="background: url(/static/icons/feed.png) no-repeat">Atom</a>
        possibles = []
        for a in soup.find_all("a"):
            norm = " " + a.text.lower().strip() + " "
            url = self._expand_url(register.repo_url, a.get("href"))
            if " rss " in norm:
                possibles.append((url, "rss"))
            elif " atom " in norm:
                possibles.append((url, "atom"))

        for url, t in possibles:
            feed = info.feed(url)
            if feed.bozo > 0:
                continue
            api = {"api_type" : t, "base_url" : url}
            v = self.version_map.get(feed.version)
            api["version"] = v

            log.info(api.get("api_type") + " at " + api.get("base_url") + " detected from html body")
            register.add_api_object(api)

class OAI_PMH(Detector):
    guesses = [
        "/oai",
        "/oaipmh",
        "/oai-pmh",
        "/oai/request",
        "/dspace-oai/request",
        "/cgi/oai2",
        "/cgi-bin/oai.exe",
        "/do/oai/"
    ]
    def name(self):
        return "OAI-PMH"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        oai = None
        for guess in self.guesses:
            url = self._expand_url(register.repo_url, guess)
            resp = info.url_get(url + "?verb=Identify")
            if resp is None:
                continue
            if resp.status_code == requests.codes.ok:
                oai = url
                break

        if oai is None:
            log.info("Unable to locate OAI-PMH endpoint which responds")
            return

        # we have an oai endpoint

        # have a go at getting the version
        doc = info.xml(oai + "?verb=Identify")
        if doc is None:
            log.info("Detected possible OAI-PMH at " + oai + " but unable to parse feed")
            return

        info.set("oai_identify", url + "?verb=Identify")
        log.info("OAI-PMH found by guessing at " + oai)
        api = {"api_type" : "oai-pmh", "base_url" : oai}

        root = doc.getroot()
        pvs = root.xpath("//*[local-name() = 'protocolVersion']")
        if len(pvs) > 0:
            v = pvs[0].text
            api["version"] = v

        lmfdoc = info.xml(oai + "?verb=ListMetadataFormats")
        lmf = lmfdoc.getroot()
        for element in lmf.xpath("//*[local-name() = 'metadataFormat']"):
            prefix = None
            namespace = None
            schema = None
            for c in element.getchildren():
                if c.tag.endswith("metadataPrefix"):
                    prefix = c.text.strip()
                if c.tag.endswith("metadataNamespace"):
                    namespace = c.text.strip()
                if c.tag.endswith("schema"):
                    schema = c.text.strip()

            format = {}
            if prefix is not None:
                format["prefix"] = prefix
            if namespace is not None:
                format["namespace"] = namespace
            if schema is not None:
                format["schema"] = schema

            if "metadata_formats" not in api:
                api["metadata_formats"] = []
            api["metadata_formats"].append(format)

        register.add_api_object(api)

class Sword(Detector):
    guesses = [
        "/sword/servicedocument",
        "/sword/service-document",
        "/swordv2/servicedocument",
        "/swordv2/service-document",
        "/dspace-sword/servicedocument",
        "/dspace-swordv2/servicedocument",
        "/sword-app/servicedocument"
    ]

    def name(self):
        return "Sword"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # first check standard sword auto-discovery
        # <html:link rel="sword" href="[Service Document URL]"/> <!-- probably v1 -->
        # <html:link rel="http://purl.org/net/sword/discovery/service-document" href="[Service Document URL]"/> <!-- probably v2 -->
        soup = info.soup(register.repo_url)
        if soup is not None:
            links = soup.find_all("link")
            for link in links:
                rels = link.get("rel")
                if rels is None:
                    continue

                # the swordv1 case
                if "sword" in rels:
                    path = link.get("href")
                    url = self._expand_url(register.repo_url, path)
                    api = {"api_type" : "sword", "version" : "1.3", "base_url" : url}
                    self._add_info(api, info)
                    log.info("Found SWORD 1.3 url in link headers: " + url)
                    register.add_api_object(api)

                # the swordv2 case
                if "http://purl.org/net/sword/discovery/service-document" in rels:
                    path = link.get("href")
                    url = self._expand_url(register.repo_url, path)
                    api = {"api_type" : "sword", "version" : "2.0", "base_url" : url}
                    self._add_info(api, info)
                    log.info("Found SWORD 2.0 url in link headers: " + url)
                    register.add_api_object(api)

        # now try the standard guesses
        for guess in self.guesses:
            url = self._expand_url(register.repo_url, guess)
            resp = info.url_get(url)
            if resp is None:
                continue
            if not (resp.status_code == requests.codes.ok or resp.status_code == 401 or resp.status_code == 403):
                continue

            api = {"api_type" : "sword", "base_url" : url}
            self._guess_version(api, register)
            self._add_info(api, info)
            log.info("Found SWORD url by guessing: " + url)
            register.add_api_object(api)

    def _add_info(self, api, info):
        resp = info.url_get(api["base_url"])
        if resp.status_code == 401 or resp.status_code == 403:
            api["authenticated"] = True
        elif resp.status_code == requests.codes.ok:
            api["authenticated"] = False

    def _guess_version(self, api, register):
        if "swordv2" in api["base_url"] or "sword2" in api["base_url"]:
            api["version"] = "2.0"
            return
        if "swordv1" in api["base_url"] or "sword1" in api["base_url"]:
            api["version"] = "1.3"
            return

        for name, version, url in register.software:
            if name == "EPrints":
                if version.startswith("3.2"):
                    api["version"] = "1.3"
                elif version.startswith("3.3"):
                    api["version"] = "2.0"
            if name == "DSpace":
                if "/sword/" in api["base_url"]:
                    api["version"] = "1.3"

class OpenSearch(Detector):
    def name(self):
        return "OpenSearch"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # <link type="application/opensearchdescription+xml" rel="search" href="http://www.repository.cam.ac.uk:80/open-search/description.xml" title="DSpace" />
        soup = info.soup(register.repo_url)
        if soup is not None:
            for link in soup.find_all("link"):
                if link.get("type") == "application/opensearchdescription+xml":
                    api = {"api_type" : "opensearch", "base_url" : link.get("href")}
                    self._detect_version(api, info)
                    register.add_api_object(api)
                    log.info("Found opensearch in link headers: " + api["base_url"])

    def _detect_version(self, api, info):
        osdoc = info.xml(api["base_url"])
        root = osdoc.getroot()
        if 'http://a9.com/-/spec/opensearch/1.1/' in root.nsmap.values():
            api["version"] = "1.1"
        else:
            api["version"] = "1.0"

class Title(Detector):
    def name(self):
        return "Title"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # get it from oai Identify
        identify_url = info.get("oai_identify")
        identify = None
        if identify_url is not None:
            identify = info.xml(identify_url)
        if identify is not None:
            root = identify.getroot()
            rn = root.xpath("//*[local-name() = 'repositoryName']")
            if len(rn) > 0:
                name = rn[0].text
                register.repo_name = name
                return

        # get it from atom feed title
        atom_urls = register.get_api(type="atom")
        for atom_url in atom_urls:
            atom = info.feed(atom_url)
            try:
                name = atom.feed.title
                register.repo_name = name
                return
            except:
                pass

        # get it from rss feed title
        rss_urls = register.get_api(type="rss")
        for rss_url in rss_urls:
            rss = info.feed(rss_url)
            try:
                name = rss.feed.title
                register.repo_name = name
                return
            except:
                pass

        # html title element of home page
        soup = info.soup(register.repo_url)
        if soup is not None:
            titles = soup.find_all("title")
            if len(titles) > 0:
                name = titles[0].text
                register.repo_name = name
                return

class Description(Detector):
    def name(self):
        return "Description"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        atom_desc = ""
        rss_desc = ""
        p_desc = ""
        td_desc = ""

        # get it from atom feed subtitle
        atom_urls = register.get_api(type="atom")
        for atom_url in atom_urls:
            atom = info.feed(atom_url)
            try:
                atom_desc = atom.feed.subtitle
            except:
                pass

        # get it from rss feed description
        rss_urls = register.get_api(type="rss")
        for rss_url in rss_urls:
            rss = info.feed(rss_url)
            try:
                desc = rss.feed.description
                if len(desc) > len(rss_desc):
                    rss_desc = desc
            except:
                pass

        soup = info.soup(register.repo_url)
        name = register.repo_name

        # p element on home page (which ideally mentions the name) and is the longest text string
        if soup is not None:
            p_desc = self._desc_from_element(soup, "p", name)
            td_desc = self._desc_from_element(soup, "td", name)

        if name in p_desc:
            register.description = p_desc
        if name in atom_desc:
            register.description = atom_desc
        if name in rss_desc:
            register.description = rss_desc
        if name in td_desc:
            register.description = td_desc

        if len(p_desc) > 0:
            register.description = p_desc
            return
        if len(atom_desc) > 0:
            register.description = atom_desc
            return
        if len(rss_desc) > 0:
            register.description = rss_desc
            return
        if len(td_desc) > 0:
            register.description = td_desc
            return

    def _desc_from_element(self, soup, el, name=None):
        likely = ""
        fallback = ""
        ps = soup.find_all(el)
        for p in ps:
            if name is not None and name in p.text:
                if len(p.text) > len(likely):
                    likely = p.text
            if len(p.text) > len(fallback):
                fallback = p.text

        if likely != "":
            return likely
        elif fallback != "":
            return fallback
        return ""

class Twitter(Detector):
    pattern = "http[s]{0,1}://twitter.com/(.+)"

    def name(self):
        return "Twitter"

    def detectable(self, register):
        return register.repo_url is not None

    def detect(self, register, info):
        # twitter url looks like this: https://twitter.com/CamPuce
        soup = info.soup(register.repo_url)
        if soup is None:
            return

        tls = [a.get("href")
               for a in soup.find_all("a")
               if a.get("href") is not None and
                  (a.get("href").startswith("https://twitter.com") or a.get("href").startswith("http://twitter.com"))
            ]

        for tl in tls:
            m = re.match(self.pattern, tl)
            if m:
                log.info("Detected twitter " + m.group(1) + " from page scrape")
                register.twitter = m.group(1)
                return

class TechnicalContact(Detector):
    def name(self):
        return "Technical Contact"

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

        name = who.get("contact_name")
        email = who.get("email")
        address = who.get("address")
        fax = who.get("fax")
        phone = who.get("phone")

        details = {}
        if name is not None:
            details["name"] = name
        if email is not None:
            details["email"] = email
        if address is not None:
            details["address"] = address
        if fax is not None:
            details["fax"] = fax
        if phone is not None:
            details["phone"] = phone

        if len(details.keys()) == 0:
            return

        # FIXME: may want to do some geolocation on the address

        contact = {"role" : ["technical"], "details" : details}
        register.add_contact_object(contact)
        log.info("Detected technical contact from whois record")

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
    Feed,
    OAI_PMH,
    Sword,
    OpenSearch,
    Title,
    Description,
    Twitter,
    TechnicalContact
]
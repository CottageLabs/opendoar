from urllib import urlopen, urlencode
import md5
import os, re, string
from unicodedata import normalize
from functools import wraps
from flask import request, current_app, flash
from random import choice
from copy import deepcopy

from portality.view.stream import stream as rawstream

from urlparse import urlparse, urljoin

import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.Utils import COMMASPACE, formatdate
from email import Encoders

from portality.core import app

import HTMLParser


def dewindows(string):
    h = HTMLParser.HTMLParser()
    try:
        string = string.decode("windows-1252")
    except:
        try:
            string = string.decode("windows-1251")
        except:
            try:
                string = string.decode("ISO-8859-1")
            except:
                try:
                    string = string.decode("utf-8")
                except:
                    pass
    try:
        string = h.unescape(string)
    except:
        pass
    return string

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    if ( test_url.scheme in ('http', 'https') and 
            ref_url.netloc == test_url.netloc ):
        return target
    else:
        return '/'

def send_mail(to, fro, subject, text, files=[], server="localhost"):
    assert type(to)==list
    assert type(files)==list
 
    msg = MIMEMultipart()
    msg['From'] = fro
    msg['To'] = COMMASPACE.join(to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject
 
    msg.attach( MIMEText(text) )
 
    for file in files:
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(file,"rb").read() )
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"'
                       % os.path.basename(file))
        msg.attach(part)
    
    # now deal with connecting to the server
    server = app.config.get("SMTP_SERVER")
    server_port = app.config.get("SMTP_PORT")
    smtp_user = app.config.get("SMTP_USER")
    smtp_pass = app.config.get("SMTP_PASS")
    
    smtp = smtplib.SMTP()  # just doing SMTP(server, server_port) does not work with Mailtrap
    # but doing .connect explicitly afterwards works both with Mailtrap and with Mandrill
    smtp.connect(server, server_port)

    if smtp_user is not None:
        smtp.login(smtp_user, smtp_pass)
    
    smtp.sendmail(fro, to, msg.as_string())
    smtp.close()


def jsonp(f):
    """Wraps JSONified output for JSONP"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            content = str(callback) + '(' + str(f(*args,**kwargs).data) + ')'
            return current_app.response_class(content, mimetype='application/javascript')
        else:
            return f(*args, **kwargs)
    return decorated_function


# derived from http://flask.pocoo.org/snippets/45/ (pd) and customised
def request_wants_json():
    best = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    if best == 'application/json' and request.accept_mimetypes[best] > request.accept_mimetypes['text/html']:
        best = True
    else:
        best = False
    if request.values.get('format','').lower() == 'json' or request.path.endswith(".json"):
        best = True
    return best
        

# derived from http://flask.pocoo.org/snippets/5/ (public domain)
# changed delimiter to _ instead of - due to ES search problem on the -
_punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')
def slugify(text, delim=u'_'):
    """Generates an slightly worse ASCII-only slug."""
    result = []
    for word in _punct_re.split(text.lower()):
        word = normalize('NFKD', word).encode('ascii', 'ignore')
        if word:
            result.append(word)
    return unicode(delim.join(result))


# get gravatar for email address
def get_gravatar(email, size=None, default=None, border=None):
    email = email.lower().strip()
    hash = md5.md5(email).hexdigest()
    args = {'gravatar_id':hash}
    if size and 1 <= int(size) <= 512:
        args['size'] = size
    if default: args['default'] = default
    if border: args['border'] = border

    url = 'http://www.gravatar.com/avatar.php?' + urlencode(args)

    response = urlopen(url)
    image = response.read()
    response.close()

    return image

def generate_password(length=8):
    chars = string.letters + string.digits
    pw = ''.join(choice(chars) for _ in range(length))
    return pw

def flash_with_url(message, category=''):
    flash(message, category + '+contains-url')
    

def dmerge(a, b):
    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dmerge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


defaultrecord = {
    "register" : {
        "operational_status" : "",
        "metadata" : [
            {
                "lang" : "en",
                "default" : True,
                "record" : {
                    "country" : "",
                    "country_code" : "",
                    "continent" : "",
                    "continent_code" : "",
                    "twitter" : "",
                    "acronym" : "",
                    "description" : "",
                    "established_date" : "",
                    "name" : "",
                    "url" : "",
                    "language" : [],
                    "language_code" : [],
                    "subject" : [
                        {
                            "term": ""
                        }
                    ],
                    "repository_type" : [],
                    "certification" : [],
                    "content_type" : []
                }
            }
        ],
        "software" : [],
        "contact" : [],
        "organisation" : [],
        "policy" : [],
        "api" : [],
        "integration": []
    }
}


dropdowns = {
    "operational_status": rawstream(key="register.operational_status",raw=True),

    "metadata_country": rawstream(key="register.metadata.record.country",raw=True),
    "metadata_country_code": rawstream(key="register.metadata.record.country_code",raw=True),
    "metadata_continent": rawstream(key="register.metadata.record.continent",raw=True),
    "metadata_continent_code": rawstream(key="register.metadata.record.continent_code",raw=True),
    "metadata_language": rawstream(key="register.metadata.record.language",raw=True),
    "metadata_language_code": rawstream(key="register.metadata.record.language_code",raw=True),
    "metadata_repository_type": rawstream(key="register.metadata.record.repository_type",raw=True),
    "metadata_content_type": rawstream(key="register.metadata.record.content_type",raw=True),
    "metadata_certification": rawstream(key="register.metadata.record.certification",raw=True),
    "metadata_subject": rawstream(key="register.metadata.record.subject.term",raw=True),

    "org_name": rawstream(key="register.organisation.details.name",raw=True),

    "contact_name": rawstream(key="register.contact.details.name",raw=True),

    "api_type": rawstream(key="register.api.api_type",raw=True),
    
    "software_name": rawstream(key="register.software.name",raw=True)
}


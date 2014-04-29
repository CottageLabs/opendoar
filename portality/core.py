import os, requests, json, esprit
from flask import Flask
from functools import wraps

from portality import settings
from flask.ext.login import LoginManager, current_user
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    configure_app(app)
    if app.config.get('INITIALISE_INDEX',False): initialise_index(app)
    setup_jinja(app)
    setup_error_email(app)
    login_manager.setup_app(app)
    return app

def configure_app(app):
    app.config.from_object(settings)
    # parent directory
    here = os.path.dirname(os.path.abspath( __file__ ))
    config_path = os.path.join(os.path.dirname(here), 'app.cfg')
    if os.path.exists(config_path):
        app.config.from_pyfile(config_path)

def initialise_index(app):
    mappings = app.config["MAPPINGS"]
    conn = esprit.raw.Connection(app.config['ELASTIC_SEARCH_HOST'], app.config['ELASTIC_SEARCH_DB'])
    if not esprit.raw.index_exists(conn):
        print "Creating Index; host:" + str(conn.host) + " port:" + str(conn.port) + " db:" + str(conn.index)
        esprit.raw.create_index(conn)
    for key, mapping in mappings.iteritems():
        if not esprit.raw.has_mapping(conn, key):
            r = esprit.raw.put_mapping(conn, key, mapping)
            print key, r.status_code
    
def setup_error_email(app):
    ADMINS = app.config.get('ADMINS', '')
    if not app.debug and ADMINS:
        import logging
        from logging.handlers import SMTPHandler
        mail_handler = SMTPHandler('127.0.0.1',
                                   'server-error@no-reply.com',
                                   ADMINS, 'error')
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

def setup_jinja(app):
    '''Add jinja extensions and other init-time config as needed.'''

    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.add_extension('jinja2.ext.loopcontrols')
    app.jinja_env.globals['getattr'] = getattr

    # a jinja filter that prints to the Flask log
    def jinja_debug(text):
        print text
        return ''
    app.jinja_env.filters['debug']=jinja_debug

app = create_app()

# a decorator to be used elsewhere (or in this file) in the app,
# anywhere where a view f() should be served only over SSL
def ssl_required(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if app.config.get("SSL"):
            if request.is_secure:
                return fn(*args, **kwargs)
            else:
                return redirect(request.url.replace("http://", "https://"))
        
        return fn(*args, **kwargs)
            
    return decorated_view

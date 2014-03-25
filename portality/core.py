import os, requests, json, esprit
from flask import Flask

from portality import settings
#from flask.ext.login import LoginManager, current_user
#login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    configure_app(app)
    if app.config.get('INITIALISE_INDEX',False): initialise_index(app)
    setup_error_email(app)
    #login_manager.setup_app(app)
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

app = create_app()


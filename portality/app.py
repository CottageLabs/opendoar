from flask import Flask, request, abort, render_template, redirect, make_response, flash
from flask.views import View
from flask.ext.login import login_user, current_user

import json

import portality.models as models
import portality.util as util
from portality.core import app, login_manager
from portality import settings, searchurl
from portality.oarr import OARRClient

from portality.view.stream import blueprint as stream
from portality.view.duplicate import blueprint as duplicate
from portality.view.duplicate import duplicate as rawduplicate
from portality.view.admin import blueprint as admin
from portality.view.account import blueprint as account
from portality.view.pagemanager import blueprint as pagemanager

from portality.autodiscovery import autodiscovery

@login_manager.user_loader
def load_account_for_login_manager(userid):
    out = models.Account.pull(userid)
    return out

@app.before_request
def standard_authentication():
    """Check remote_user on a per-request basis."""
    remote_user = request.headers.get('REMOTE_USER', '')
    if remote_user:
        user = models.Account.pull(remote_user)
        if user:
            login_user(user, remember=False)
    # add a check for provision of api key
    elif 'api_key' in request.values:
        res = models.Account.query(q='api_key:"' + request.values['api_key'] + '"')['hits']['hits']
        if len(res) == 1:
            user = models.Account.pull(res[0]['_source']['id'])
            if user:
                login_user(user, remember=False)


@app.context_processor
def set_current_context():
    """ Set some template context globals. """
    return dict(current_user=current_user, app=app)


app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(account, url_prefix='/account')
app.register_blueprint(duplicate, url_prefix='/duplicate')
app.register_blueprint(stream, url_prefix='/stream')
#app.register_blueprint(pagemanager)


@app.route("/")
def root():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/tools")
def tools():
    return render_template("tools.html")

@app.route("/community")
def community():
    return render_template("community.html")

@app.route("/stats")
def stats():
    return render_template("stats.html")

@app.route("/search")
def search():
    return render_template("search.html", api_base_url=app.config.get("OARR_API_BASE_URL", "http://localhost:5001/"))

@app.route("/map")
def mapp():
    return render_template("map.html")

@app.route("/autodetect")
def autodetect():
    return render_template("autodetect.html")

@app.route("/registryfile")
def registryfile():
    return render_template("registryfile.html")

@app.route("/registryfile/validate", methods=["GET", "POST"])
def validate_registry_file():
    if request.method == "GET":
        return render_template("registryfile_validate.html")
    else:
        obj = None
        url = request.values.get("url")
        if url is not None and url != "":
            try:
                obj = autodiscovery.validate_registry_file(registry_file_url=url)
            except autodiscovery.registryfile.RegistryFileException as e:
                return render_template("registryfile_validation_results.html", exception=e)
        elif request.files['upload']:
            file = request.files["upload"]
            content = file.read()
            try:
                obj = autodiscovery.validate_registry_file(registry_file_content=content)
            except autodiscovery.registryfile.RegistryFileException as e:
                return render_template("registryfile_validation_results.html", exception=e)

        if obj is not None:
            reg = autodiscovery.registryfile.RegistryFile.expand(obj)
            return render_template("registryfile_validation_results.html", repo=reg)
        else:
            flash("You did not provide a URL or a file to validate", "error")
            return render_template("registryfile_validate.html", )

@app.route("/contribute", methods=["GET","POST"])
def contribute():

    detectdone = False
    dup = False

    if request.method == 'GET':
    
        # check to see if this is an update
        if 'updaterequest' in request.values:
            # get record from OARR
            try:
                base = app.config.get("OARR_API_BASE_URL")
                if base is None: abort(500)
                client = OARRClient(base)
                record = client.get_record(request.values["updaterequest"]).raw
                if "opendoar" not in record["admin"]: record["admin"]["opendoar"] = {}
                record["admin"]["opendoar"]["updaterequest"] = request.values["updaterequest"]
                detectdone = True
            except:
                abort(404)
        
        # check for a url request param
        elif 'url' in request.values:
            # if there is one, then try to set the initial object
            if len(request.values['url']) != 0:
                try:
                    register = autodiscovery.discover(request.values['url'])
                    record = register.raw
                    for k, v in util.defaultrecord['register']['metadata'][0]['record'].iteritems():
                        if k not in record.get('register',{}).get('metadata',[{"record":{}}])[0]['record']:
                            record['register']['metadata'][0]['record'][k] = v
                except:
                    record = util.defaultrecord

                # check if there is already a record with this url
                dup = rawduplicate(request.values['url'],raw=True)
                
            else:
                record = util.defaultrecord
            detectdone = True
        else:
            # otherwise set a default initial object
            record = util.defaultrecord
            
        if util.request_wants_json():
            resp = make_response( json.dumps({"record":record}) )
            resp.mimetype = "application/json"
            return resp
        else:
            return render_template("contribute.html", record=record, detectdone=detectdone, duplicate=dup)

    elif request.method == 'POST':
        base = app.config.get("OARR_API_BASE_URL")
        apikey = app.config.get("OARR_API_KEY")
        if base is None or apikey is None: abort(500)
        client = OARRClient(base, apikey)
        record = client.prep_record(util.defaultrecord,request)
        if 'updaterequest' not in record['admin']['opendoar']: record['admin']['opendoar']['newcontribution'] = True
        saved = client.save_record(record)
        if saved:
            flash('Thank you very much for your submission. Your request will be processed as soon as possible, and usually within three working days.', 'success')
            return redirect('/')
        else:
            flash('Sorry, there was a problem saving your submission. Please try again.', 'error')
            return redirect('/contribute')
    

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/repository/<repo_id>")
def repository(repo_id):
    base = app.config.get("OARR_API_BASE_URL")
    if base is None:
        abort(500)
    client = OARRClient(base)
    if util.request_wants_json():
        repo_id = repo_id.replace('.json','')
        try:
            record = client.get_record(repo_id)
            resp = make_response( record.json )
            resp.mimetype = "application/json"
            return resp        
        except:
            abort(404)
    else:
        record = client.get_record(repo_id)
        if record is None:
            abort(404)
        return render_template("repository.html", repo=record, searchurl=searchurl, search_similar=True)


@app.route("/organisation/<org>")
def organisation(org):
    base = app.config.get("OARR_API_BASE_URL")
    if base is None:
        abort(500)
    client = OARRClient(base)
    if util.request_wants_json():
        org = org.replace('.json','')
        try:
            record = client.get_org(org)
            resp = make_response( record.json )
            resp.mimetype = "application/json"
            return resp        
        except:
            abort(404)
    else:
        try:
            record = client.get_org(org)
            return render_template("organisation.html", org=record.record)
        except:
            abort(404)

@app.route("/detect", methods=["GET", "POST"])
def detect():
    if request.method == "GET":
        return render_template("detect.html")
    if request.method == "POST":
        url = request.values.get("url")
        if url is None:
            return render_template("detect.html")
        register = autodiscovery.discover(url)
        if util.request_wants_json():
            resp = make_response( json.dumps(register) )
            resp.mimetype = "application/json"
            return resp        
        else:
            return render_template("repository.html", repo=register, searchurl=searchurl)

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=app.config['PORT'])


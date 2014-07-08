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

from portality.view.admin import blueprint as admin
from portality.view.account import blueprint as account

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

app.register_blueprint(stream, url_prefix='/stream')

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


@app.route("/contribute", methods=['GET','POST'])
def contribute():

    if request.method == 'GET':
    
        # check for a url request param
        if 'url' in request.values:
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
            else:
                record = util.defaultrecord
            record["detectdone"] = True
        else:
            # otherwise set a default initial object
            record = util.defaultrecord

        print record

        if util.request_wants_json():
            resp = make_response( json.dumps({"record":record,"dropdowns":util.dropdowns}) )
            resp.mimetype = "application/json"
            return resp
        else:
            return render_template("contribute.html", dropdowns=util.dropdowns, record=record)

    elif request.method == 'POST':
        base = app.config.get("OARR_API_BASE_URL")
        apikey = app.config.get("OARR_API_KEY")
        if base is None or apikey is None: abort(500)
        client = OARRClient(base, apikey)
        record = client.prep_record(util.defaultrecord,request)
        #client.save_record(record)
        flash('Thanks for your contribution - your record will be processed soon', 'success')
        return redirect('/')
    

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
        try:
            record = client.get_record(repo_id)
            return render_template("repository.html", repo=record, searchurl=searchurl)
        except:
            abort(404)


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


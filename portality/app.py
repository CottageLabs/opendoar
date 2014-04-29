from flask import Flask, request, abort, render_template, redirect, make_response
from flask.views import View
from flask.ext.login import login_user, current_user

import portality.models as models
from portality.core import app, login_manager
from portality import settings, searchurl
from portality.oarr import OARRClient

from portality.view.stream import blueprint as stream
from portality.view.stream import stream as rawstream

from portality.view.admin import blueprint as admin
from portality.view.account import blueprint as account

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


app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(account, url_prefix='/account')

app.register_blueprint(stream, url_prefix='/stream')

@app.route("/")
def root():
    return render_template("index.html", api_base_url=app.config.get("OARR_API_BASE_URL", "http://localhost:5001/"))

@app.route("/map")
def mapp():
    return render_template("map.html")


@app.route("/contribute")
def contribute():

    autos = {
        "org.name": rawstream(key="register.organisation.details.name",raw=True),
        "api.type": rawstream(key="register.api.api_type",raw=True),
        "policy.terms": rawstream(key="register.policy.policy_terms",raw=True)
    }
    dropdowns = {
        "ops": rawstream(key="register.operational_status",raw=True),
        "contents": rawstream(key="register.metadata.record.content_type",raw=True,size=10000),
        "subjects": rawstream(key="register.metadata.record.subject.term",raw=True,size=10000),
        "types": rawstream(key="register.metadata.record.repository_type",raw=True),
        "softwares": rawstream(key="register.software.name",raw=True),
        "policytypes": rawstream(key="register.policy.policy_type",raw=True),
        "policygrades": rawstream(key="register.policy.policy_grade",raw=True)
    }
    return render_template("contribute.html",autos=autos,dropdowns=dropdowns)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/repository/<repo_id>")
def repository(repo_id):
    base = app.config.get("OARR_API_BASE_URL")
    if base is None:
        abort(500)
    client = OARRClient(base)
    if repo_id.endswith('.json'):
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
    if org.endswith('.json'):
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


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=app.config['PORT'])


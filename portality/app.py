from flask import Flask, request, abort, render_template, redirect, make_response
from flask.views import View
from flask.ext.login import login_user, current_user

import portality.models as models
from portality.core import app#, login_manager
from portality import settings, searchurl
from portality.oarr import OARRClient


@app.route("/")
def root():
    return render_template("index.html", api_base_url=app.config.get("OARR_API_BASE_URL", "http://localhost:5001/"))

@app.route("/map")
def mapp():
    return render_template("map.html")


@app.route("/contribute")
def contribute():
    return render_template("contribute.html")


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
        #try:
        record = client.get_org(org)
        return render_template("organisation.html", org=record.record)
        #except:
        #    abort(404)


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=app.config['PORT'])


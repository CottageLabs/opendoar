from flask import Blueprint, request, flash, abort, make_response
from flask import render_template, redirect, url_for
from flask.ext.login import current_user, login_required

from portality.core import app

import portality.util as util

from portality.view.duplicate import duplicate as duplicate

from portality.oarr import OARRClient
import json, time

blueprint = Blueprint('admin', __name__)


# restrict everything in admin to logged in users
@blueprint.before_request
def restrict():
    if current_user.is_anonymous():
        return redirect('/account/login?next=' + request.path)


# build an admin page where things can be done
@blueprint.route('/')
def index():

    base = app.config.get("OARR_API_BASE_URL")
    if base is None: abort(500)
    client = OARRClient(base)

    # run some queries to build up some stats for the page
    qr = {
        "query":{
            "bool":{
                "should":[
                    {
                        "term": {
                            "admin.opendoar.in_opendoar":False
                        }
                    },
                    {
                        "constant_score": {
                            "filter": {
                                "missing": {"field": "admin.opendoar.in_opendoar"}
                            }
                        }
                    }

                ]
            }
        },
        "sort": [{"last_updated":{"order":"desc"}}],
        "size":0
    }

    stats = {}
    
    # get number not in_opendoar
    res = client.query(qr)
    stats['out'] = res.get('hits',{}).get('total',0)
    
    # get recently edited in opendoar and not since saved
    qr['query']['bool']['must'] = [{'term': {'admin.opendoar.in_opendoar': True}}]
    qr['query']['bool']['must'] = [{'constant_score': {'filter': {'exists': {'field': 'admin.opendoar.last_saved'}}}}]
    del qr['query']['bool']['should']
    qr['filter'] = {
        "script" : {
            "script" : "unviewed"
            #"script" : "doc['last_updated'].value > doc['admin.opendoar.last_saved'].value"
        }
    }
    res = client.query(qr)
    try:
        stats['unviewed'] = res['hits']['total']
    except:
        stats['unviewed'] = 'MISSING SCRIPT?'

    # get update requests
    qr = {
        "query":{
            "bool":{
                "must":[
                    {
                        "constant_score": {
                            "filter": {
                                "exists": {
                                    "field": "admin.opendoar.updaterequest"
                                }
                            }
                        }
                    }
                ]
            }
        },
        "sort": [{"last_updated":{"order":"desc"}}],
        "size":0
    }
    res = client.query(qr)
    stats['updaterequest'] = res.get('hits',{}).get('total',0)

    # get new contributions
    qr = {
        "query":{
            "bool":{
                "must":[
                    {
                        "constant_score": {
                            "filter": {
                                "exists": {
                                    "field": "admin.opendoar.newcontribution"
                                }
                            }
                        }
                    }
                ]
            }
        },
        "sort": [{"last_updated":{"order":"desc"}}],
        "size":0
    }
    res = client.query(qr)
    stats['newcontribution'] = res.get('hits',{}).get('total',0)

    return render_template('admin/index.html', stats=stats)


# show a particular student record for editing
@blueprint.route('/record')
@blueprint.route('/record/<uuid>', methods=['GET','POST','DELETE'])
def record(uuid=None):

    base = app.config.get("OARR_API_BASE_URL")
    apikey = app.config.get("OARR_API_KEY")
    if base is None or apikey is None: abort(500)
    client = OARRClient(base, apikey)

    detectdone = False
    dup = False

    if request.method == 'GET':

        if uuid is None or uuid == "new":
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
                detectdone = True

                # check if there is already a record with this url
                dup = duplicate(request.values['url'],raw=True)

            else:
                # otherwise set a default initial object
                record = util.defaultrecord
                

        else:
            # get record from OARR
            try:
                record = client.get_record(uuid.replace('.json','')).raw
                detectdone = True

                # check if there is already a record with this url
                dup = duplicate(record['register']['metadata'][0]['record']['url'],raw=True)
                
            except:
                abort(404)

        if util.request_wants_json():
            resp = make_response( json.dumps({"record":record}) )
            resp.mimetype = "application/json"
            return resp
        else:
            return render_template("contribute.html", record=record, detectdone=detectdone, duplicate=dup)

    elif ( request.method == 'POST' and request.values.get('submit','') == "Delete" ) or request.method == 'DELETE':
        record = client.get_record(uuid)
        if record is None: abort(404)
        client.delete_record(uuid)
        time.sleep(1)
        flash("Record delete")
        return redirect(url_for('.index'))

    elif request.method == 'POST':
        if uuid == 'new':
            # save the new record to OARR
            record = client.prep_record(util.defaultrecord,request)
            saved = client.save_record(record)

            if saved:
                flash("New record created", "success")
                return redirect(url_for('.index'))
            else:
                flash("Sorry, the attempt to create a new record was unsuccessful", "error")
                return redirect("/admin/record/new")
        else:
            rec = client.get_record(uuid)
            if rec is None: abort(404)

            # remove any newcontribution tag on first save via admin
            if "newcontribution" in  rec.raw.get("admin",{}).get("opendoar",{}):
                del rec.raw['admin']['opendoar']['newcontribution']
            
            # if this is an update acceptance, do the update
            if "updaterequest" in rec.raw.get("admin",{}).get("opendoar",{}):
                # get the original record, prep it with the update, delete the update request record
                forupdate = client.get_record(rec.raw["admin"]["opendoar"]["updaterequest"])
                if forupdate is None:
                    flash("Sorry, an original record cannot be found to correspond with this update request.", "error")
                    return redirect('/admin/record/' + uuid)
                else:
                    record = client.prep_record(forupdate.raw,request)
                    try:
                        del record["admin"]["opendoar"]["updaterequest"]
                        saved = client.save_record(record)
                        if saved:
                            client.delete_record(uuid)
                            time.sleep(1)
                            flash("This original record has been successfully updated, and the update request record has been deleted.", "success")
                            return redirect('/admin/record/' + str(record["id"]))
                        else:
                            flash("Sorry, there was an error. Your changes have not been saved. Please try again.", "error")
                            return redirect('/admin/record/' + uuid)
                    except:
                        flash("Sorry, there was an error. Your changes have not been saved. Please try again.", "error")
                        return redirect('/admin/record/' + uuid)

            # otherwise save the record changes to OARR
            else:
                # do whatever needs done here to update the record from the form input
                record = client.prep_record(rec.raw,request)
                saved = client.save_record(record)
    
                if saved:
                    detectdone = True
                    time.sleep(1)
                    flash("Record has been updated", "success")
                    return render_template(
                        'contribute.html', 
                        record=record,
                        detectdone=detectdone,
                        duplicate=dup
                    )
                else:
                    flash("Sorry, there was an error. Your changes have not been saved. Please try again.", "error")
                    return redirect('/admin/record/' + uuid)
                

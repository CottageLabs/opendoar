from flask import Blueprint, request, flash, abort, make_response
from flask import render_template, redirect, url_for
from flask.ext.login import current_user, login_required

from portality.core import app

import portality.util as util

from portality.oarr import OARRClient
import json

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
                "must":[
                    {
                        "term": {
                            "admin.opendoar.in_opendoar":False
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
    stats['out'] = res['hits']['total']
    
    # get recently created not in opendoar and not yet viewed
    qr['filter'] = {
        "script" : {
            "script" : "doc['created_date'].value == doc['last_updated'].value"
        }
    }
    res = client.query(qr)
    print json.dumps(res,indent=4)
    stats['unviewed'] = res['hits']['total']

    return render_template('admin/index.html', stats=stats)


# show a particular student record for editing
@blueprint.route('/record')
@blueprint.route('/record/<uuid>', methods=['GET','POST','DELETE'])
def record(uuid=None):

    base = app.config.get("OARR_API_BASE_URL")
    if base is None: abort(500)
    client = OARRClient(base)

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
                record["detectdone"] = True
            else:
                # otherwise set a default initial object
                record = util.defaultrecord

        else:
            # get record from OARR
            record = client.get_record(uuid)
            if record is None: abort(404)

        if util.request_wants_json():
            resp = make_response( json.dumps({"record":record,"dropdowns":util.dropdowns}) )
            resp.mimetype = "application/json"
            return resp
        else:
            return render_template("contribute.html", dropdowns=util.dropdowns, record=record)

    elif ( request.method == 'POST' and request.values.get('submit','') == "Delete" ) or request.method == 'DELETE':
        record = client.get_record(uuid)
        if record is None: abort(404)
        # this should perform a delete
        time.sleep(1)
        flash("Record not deleted - there is no delete functionality yet")
        return redirect(url_for('.index'))

    elif request.method == 'POST':
        if uuid == 'new':
            record = client.get_record(uuid)
            if record is None: abort(404)

            # save the new record to OARR

            flash("New record created", "success")
            return redirect(url_for('record') + '/' + str(record['id']))
        else:
            record = client.get_record(uuid)
            if record is None: abort(404)

            # save the changes to OARR

            flash("Record has been updated", "success")
            return render_template(
                'contribute.html', 
                record=record, 
                dropdowns=util.dropdowns
            )
            

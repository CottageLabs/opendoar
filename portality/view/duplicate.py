
import json

from flask import Blueprint, request, abort, make_response

from portality.core import app

from portality.oarr import OARRClient


blueprint = Blueprint('duplicate', __name__)


@blueprint.route("/")
def duplicate(url=False,raw=False):
    if 'url' in request.values: url = request.values['url']
    if url:
        turl = '*' + url.replace('http://','').replace('https://','').replace('www','').strip('/') + '*'
        base = app.config.get("OARR_API_BASE_URL")
        if base is None: abort(500)
        client = OARRClient(base)
        r = client.query(qry={'query':{'query_string':{"query":turl}}})
        if r.get('hits',{}).get('total',0) != 0:
            res = r['hits']['hits'][0]['_id']
        else:
            res = False
    else:
        res = False

    if raw:
        return res
    else:
        resp = make_response( json.dumps(res) )
        resp.mimetype = "application/json"
        return resp




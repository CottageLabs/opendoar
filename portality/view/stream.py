'''
A simple endpoint for streaming out various bits of data from your index, useful for 
autocompletes and things like that on your front end. Just access indextype/key, 
and use the usual ES params for paging and querying. Returns back a list of values.
'''

import json

from flask import Blueprint, request, abort, make_response

from portality.core import app

from portality.oarr import OARRClient


blueprint = Blueprint('stream', __name__)

# implement a JSON stream that can be used for autocompletes
# index type and key to choose should be provided, and can be comma-separated lists
# "q" param can provide query term to filter by
# "counts" param indicates whether to return a list of strings or a list of lists [string, count]
# "size" can be set to get more back
@blueprint.route('/')
@blueprint.route('/<index>')
@blueprint.route('/<index>/<key>')
def stream(index='record',key='register.metadata.record.subject.term',size=1000,raw=False,q=False,counts=False,order='term'):

    indices = []
    for idx in index.split(','):
        if idx not in app.config['NO_QUERY']:
            indices.append(idx)

    if not isinstance(key,list):
        keys = key.split(',')

    if not counts: counts = request.values.get('counts',False)

    if request.values.get('order',False): order = request.values['order']

    if not q: q = request.values.get('q','*')
    if not q.endswith("*") and "~" not in q: q += "*"
    if not q.startswith("*") and "~" not in q: q = "*" + q

    qry = {
        'query':{'match_all':{}},
        'size': 0,
        'facets':{}
    }
    if q != "*": qry['query'] = {"query_string": {"query": q}}
    for ky in keys:
        ks = ky.replace('.exact','')
        qry['facets'][ks] = {"terms":{"field":ks+app.config['FACET_FIELD'],"order":order, "size":request.values.get('size',size)}}
        
    base = app.config.get("OARR_API_BASE_URL")
    if base is None:
        abort(500)
    client = OARRClient(base)
    try:
        r = client.query(qry).json()
    except:
        r = {}
    
    res = []
    try:
        if counts:
            for k in keys:
                ks = k.replace('.exact','')
                res = res + [[i['term'],i['count']] for i in r.get('facets',{}).get(ks,{}).get("terms",[])]
        else:
            for k in keys:
                ks = k.replace('.exact','')
                res = res + [i['term'] for i in r.get('facets',{}).get(ks,{}).get("terms",[])]
    except:
        pass

    if raw:
        return res
    else:
        resp = make_response( json.dumps(res) )
        resp.mimetype = "application/json"
        return resp


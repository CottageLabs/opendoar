from copy import deepcopy
import json

_filter_query = {
    "query":{"filtered":{
        "query":{"match_all":{}},
        "filter":{"bool":{"must":[]}}}
    }
}

def software(name):
    query = deepcopy(_filter_query)
    st = {"term" : {"register.software.name.exact" : name}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(st)
    return _search_url(query)

def repository_type(t):
    query = deepcopy(_filter_query)
    rt = {"term" : {"register.metadata.record.repository_type.exact" : t}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(rt)
    return _search_url(query)

def api_type(t):
    query = deepcopy(_filter_query)
    at = {"term" : {"register.api.api_type.exact" : t}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(at)
    return _search_url(query)

def content_type(t):
    query = deepcopy(_filter_query)
    ct = {"term" : {"register.metadata.record.content_type.exact" : t}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(ct)
    return _search_url(query)

def subject(t):
    query = deepcopy(_filter_query)
    st = {"term" : {"register.metadata.record.subject.term.exact" : t}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(st)
    return _search_url(query)

def country(c):
    query = deepcopy(_filter_query)
    st = {"term" : {"register.metadata.record.country.exact" : c}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(st)
    return _search_url(query)

def continent(c):
    query = deepcopy(_filter_query)
    st = {"term" : {"register.metadata.record.continent.exact" : c}}
    query["query"]["filtered"]["filter"]["bool"]["must"].append(st)
    return _search_url(query)

def _search_url(query):
    return "/?source=" + json.dumps(query)
    

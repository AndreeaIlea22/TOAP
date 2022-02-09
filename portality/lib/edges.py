# ~~EdgesIntegration:Library~~
# ~~-> Edges:Technology~~
# ~~-> Elasticsearch:Technology~~

from urllib import parse
import json


def make_url_query(**params):
    query = make_query(**params)
    return parse.quote_plus(json.dumps(query))


def make_query(**params):
    gsq = GeneralSearchQuery(**params)
    return gsq.query()


class GeneralSearchQuery(object):
    def __init__(self, terms=None, query_string=None):
        self.terms = None if terms is None else terms if isinstance(terms, list) else [terms]
        self.query_string = query_string

    def query(self):
        musts = []
        if self.terms is not None:
            for term in self.terms:
                musts.append({"term": term})

        if self.query_string is not None:
            qs = {"query_string": {"default_operator": "AND", "query": self.query_string}}
            musts.append(qs)

        query = {"match_all": {}}
        if len(musts) > 0:
            query = {
                "bool": {
                    "must": musts
                }
            }

        return { "query" : query }
import requests, uuid
from collections import UserDict
from copy import deepcopy
from datetime import datetime, timedelta
import time
import re

from portality.core import app, es_connection as ES
import urllib.parse
import json
import elasticsearch

# All models in models.py should inherit this DomainObject to know how to save themselves in the index and so on.
# You can overwrite and add to the DomainObject functions as required. See models.py for some examples.


ES_MAPPING_MISSING_REGEX = re.compile(r'.*No mapping found for \[[a-zA-Z0-9-_]+?\] in order to sort on.*', re.DOTALL)
CONTENT_TYPE_JSON = {'Content-Type': 'application/json'}


class ElasticSearchWriteException(Exception):
    pass


class DomainObject(UserDict, object):
    """
    ~~DomainObject:Model->Elasticsearch:Technology~~
    """
    __type__ = None                                                       # set the type on the model that inherits this

    def __init__(self, **kwargs):
        # if self.data is already set, don't do anything here
        try:
            object.__getattribute__(self, "data")
        except:
            if '_source' in kwargs:
                self.data = dict(kwargs['_source'])
                self.meta = dict(kwargs)
                del self.meta['_source']
            else:
                self.data = dict(kwargs)
        # FIXME: calling super() breaks everything, even thought this is the correct thing to do
        # this is because the DomainObject incorrectly overrides properties of the super class
        # super(DomainObject, self).__init__()

    @classmethod
    def index_name(cls):
        if app.config['ELASTIC_SEARCH_INDEX_PER_TYPE'] and cls.__type__ is not None:
            name = ','.join([app.config['ELASTIC_SEARCH_DB_PREFIX'] + t for t in cls.__type__.split(',')])
        else:
            name = app.config['ELASTIC_SEARCH_DB']
        return name

    @classmethod
    def doc_type(cls):
        if app.config['ELASTIC_SEARCH_INDEX_PER_TYPE']:
            return None
        else:
            return cls.__type__

    # @classmethod
    # def target_whole_index(cls):
    #     t = str(app.config['ELASTIC_SEARCH_HOST']).rstrip('/') + '/'
    #     if app.config['ELASTIC_SEARCH_INDEX_PER_TYPE'] and cls.__type__ is not None:
    #         t += ','.join([app.config['ELASTIC_SEARCH_DB_PREFIX'] + t for t in cls.__type__.split(',')]) + '/'
    #     else:
    #         t += app.config['ELASTIC_SEARCH_DB'] + '/'
    #     return t
    #
    # @classmethod
    # def target(cls):
    #     t = cls.target_whole_index()
    #     # fixme: on search, the type is not necessary any more 299 Elasticsearch-7.10.2-747e1cc71def077253878a59143c1f785afa92b9 "[types removal] Specifying types in search requests is deprecated."
    #     if app.config['ELASTIC_SEARCH_INDEX_PER_TYPE']:
    #         t += app.config.get('INDEX_PER_TYPE_SUBSTITUTE', '_doc') + '/'
    #     else:
    #         t += cls.__type__ + '/'
    #     return t
    
    @classmethod
    def makeid(cls):
        """Create a new id for data object overwrite this in specific model types if required"""
        return str(uuid.uuid4().hex)

    @property
    def id(self):
        rawid = self.data.get("id", None)
        if rawid is not None:
            return str(rawid)
        return None
    
    def set_id(self, id=None):
        if id is None:
            id = self.makeid()
        self.data["id"] = str(id)
    
    @property
    def version(self):
        return self.meta.get('_version', None)

    @property
    def json(self):
        return json.dumps(self.data)
    
    def set_created(self, date=None):
        if date is None:
            self.data['created_date'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            self.data['created_date'] = date

    @property
    def created_date(self):
        return self.data.get("created_date")

    @property
    def created_timestamp(self):
        return datetime.strptime(self.data.get("created_date"), "%Y-%m-%dT%H:%M:%SZ")
    
    @property
    def last_updated(self):
        return self.data.get("last_updated")

    @property
    def last_updated_timestamp(self):
        return datetime.strptime(self.last_updated, "%Y-%m-%dT%H:%M:%SZ")

    def save(self, retries=0, back_off_factor=1, differentiate=False, blocking=False):
        """
        ~~->ReadOnlyMode:Feature~~
        :param retries:
        :param back_off_factor:
        :param differentiate:
        :param blocking:
        :return:
        """
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, save command cannot run")
            return

        if 'id' not in self.data:
            self.data['id'] = self.makeid()

        if 'es_type' not in self.data and self.__type__ is not None:
            self.data['es_type'] = self.__type__

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if (blocking or differentiate) and "last_updated" in self.data:
            diff = datetime.now() - datetime.strptime(self.data["last_updated"], "%Y-%m-%dT%H:%M:%SZ")

            # we need the new last_updated time to be later than the new one
            if diff.total_seconds() < 1:
                soon = datetime.utcnow() + timedelta(seconds=1)
                now = soon.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.data['last_updated'] = now

        if 'created_date' not in self.data:
            self.data['created_date'] = now

        attempt = 0
        d = json.dumps(self.data)
        r = None
        while attempt <= retries:
            try:
                r = ES.index(self.index_name(), d, doc_type=self.doc_type(), id=self.data.get("id"), headers=CONTENT_TYPE_JSON)
                break

            except (elasticsearch.ConnectionError, elasticsearch.ConnectionTimeout):
                app.logger.exception("Failed to connect to ES")
                attempt += 1

            except elasticsearch.TransportError as e:
                # Retries depend on which end the error lies.
                if 400 <= e.status_code < 500:
                    # Bad request, do not retry as it won't work. Fail with ElasticSearchWriteException.
                    app.logger.exception("Bad Request to ES, save failed. Details: {0}".format(e.error))
                    raise ElasticSearchWriteException(e.error)
                elif e.status_code >= 500:
                    # Server error, this could be temporary so we may want to retry
                    app.logger.exception("Server Error from ES, retrying. Details: {0}".format(e.error))
                    attempt += 1
            except Exception as e:
                # if any other exception occurs, make sure it's at least logged.
                app.logger.exception("Unhandled exception in save method of DAO")
                raise ElasticSearchWriteException(e)

            # wait before retrying
            time.sleep((2**attempt) * back_off_factor)

        if attempt > retries:
            raise DAOSaveExceptionMaxRetriesReached(
                "After {attempts} attempts the record with "
                "id {id} failed to save.".format(
                    attempts=attempt, id=self.data['id']))

        if blocking:
            bq = BlockQuery(self.id)
            while True:
                res = self.query(q=bq.query())
                j = self._unwrap_search_result(res)
                if len(j) == 0:
                    time.sleep(0.25)
                    continue
                if len(j) > 1:
                    raise Exception("More than one record with id {x}".format(x=self.id))
                if j[0].get("last_updated", [])[0] == now:
                    break
                else:
                    time.sleep(0.25)
                    continue

        return r

    def delete(self):
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, delete command cannot run")
            return

        # r = requests.delete(self.target() + self.id)
        ES.delete(self.index_name(), self.id, doc_type=self.doc_type())

    @staticmethod
    def make_query(theq=None, should_terms=None, consistent_order=True, **kwargs):
        """
        Generate a query object based on parameters but don't send to
        backend - return it instead. Must always have the same
        parameters as the query method. See query method for explanation
        of parameters.
        """
        if theq is None:
            theq = ""
        q = deepcopy(theq)
        if isinstance(q, dict):
            query = q
            if 'bool' not in query['query']:
                boolean = {'bool': {'must': []}}
                boolean['bool']['must'].append(query['query'])
                query['query'] = boolean
            if 'must' not in query['query']['bool']:
                query['query']['bool']['must'] = []
        elif q:
            query = {
                'query': {
                    'bool': {
                        'must': [
                            {'query_string': {'query': q}}
                        ]
                    }
                }
            }
        else:
            query = {
                'query': {
                    'bool': {
                        'must': [
                            {'match_all': {}}
                        ]
                    }
                }
            }

        if should_terms is not None and len(should_terms) > 0:
            for s in should_terms:
                if not isinstance(should_terms[s], list):
                    should_terms[s] = [should_terms[s]]
                query["query"]["bool"]["must"].append({"terms": {s: should_terms[s]}})

        sort_specified = False
        for k, v in kwargs.items():
            if k == '_from':
                query['from'] = v
            elif k == 'sort':
                sort_specified = True
                query['sort'] = v
            else:
                query[k] = v
        if "sort" in query:
            sort_specified = True

        if not sort_specified and consistent_order:
            # FIXME: review this - where is default sort necessary, and why do we want this in ID order?
            query['sort'] = [{"id.exact": {"order": "asc", "unmapped_type": "keyword"}}]

        return query

    @classmethod
    def _unwrap_search_result(cls, res):
        return [i.get("_source") if "_source" in i else i.get("fields") for i in
                res.get('hits', {}).get('hits', [])]

    @classmethod
    def bulk(cls, bibjson_list, idkey='id', refresh=False):
        """
        ~~->ReadOnlyMode:Feature~~
        :param bibjson_list:
        :param idkey:
        :param refresh:
        :return:
        """
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, bulk command cannot run")
            return

        data = ''
        for r in bibjson_list:
            data += json.dumps({'index': {'_id': r[idkey]}}) + '\n'
            data += json.dumps(r) + '\n'
        resp = ES.bulk(data, headers=CONTENT_TYPE_JSON)
        # r = requests.post(cls.target() + '_bulk', data=data, headers=CONTENT_TYPE_JSON)
        if refresh:
            cls.refresh()
        return resp

    @classmethod
    def refresh(cls):
        """
        ~~->ReadOnlyMode:Feature~~
        :return:
        """
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, refresh command cannot run")
            return

        # r = requests.post(cls.target() + '_refresh',  headers=CONTENT_TYPE_JSON)
        # return r.json()

        return ES.refresh(index=cls.index_name())

    @classmethod
    def pull(cls, id_):
        """Retrieve object by id."""
        if id_ is None or id_ == '':
            return None

        try:
            # out = requests.get(cls.target() + id_)
            out = ES.get(cls.index_name(), id_, doc_type=cls.doc_type())
        except elasticsearch.NotFoundError:
            return None
        except elasticsearch.TransportError as e:
            raise Exception("ES returned an error: {x}".format(x=json.dumps(e.info)))
        except Exception as e:
            return None
        if out is None:
            return None

        return cls(**out)

    @classmethod
    def pull_by_key(cls, key, value):
        res = cls.query(q={"query": {"term": {key+app.config['FACET_FIELD']: value}}})
        if res.get('hits', {}).get('total', {}).get('value', 0) == 1:
            return cls.pull(res['hits']['hits'][0]['_source']['id'])
        else:
            return None

    @classmethod
    def query(cls, q=None, **kwargs):
        """Perform a query on backend.

        :param q: maps to query_string parameter if string, or query dict if dict.
        :param kwargs: any keyword args as per
            http://www.elasticsearch.org/guide/reference/api/search/uri-request.html
        """
        query = cls.make_query(q, **kwargs)
        return cls.send_query(query)

    @classmethod
    def send_query(cls, qobj, retry=50):
        """Actually send a query object to the backend."""
        r = None
        count = 0
        exception = None
        while count < retry:
            count += 1
            try:
                # ES 7.10 updated target to whole index, since specifying type for search is deprecated
                # r = requests.post(cls.target_whole_index() + recid + "_search", data=json.dumps(qobj),  headers=CONTENT_TYPE_JSON)
                r = ES.search(body=json.dumps(qobj), index=cls.index_name(), doc_type=cls.doc_type(), headers=CONTENT_TYPE_JSON)
                break
            except Exception as e:
                exception = e
            time.sleep(0.5)
                
        if r is not None:
            return r
        if exception is not None:
            raise exception
        raise Exception("Couldn't get the ES query endpoint to respond.  Also, you shouldn't be seeing this.")

    @classmethod
    def remove_by_id(cls, id):
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, delete_by_id command cannot run")
            return

        # r = requests.delete(cls.target() + id)
        ES.delete(cls.index_name(), id)

    @classmethod
    def delete_by_query(cls, query):
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, delete_by_query command cannot run")
            return

        #r = requests.delete(cls.target() + "_query", data=json.dumps(query))
        #return r
        return ES.delete_by_query(cls.index_name(), json.dumps(query), doc_type=cls.doc_type())


    @classmethod
    def destroy_index(cls):
        if app.config.get("READ_ONLY_MODE", False) and app.config.get("SCRIPTS_READ_ONLY_MODE", False):
            app.logger.warn("System is in READ-ONLY mode, destroy_index command cannot run")
            return

        # if app.config['ELASTIC_SEARCH_INDEX_PER_TYPE']:
        #     return esprit.raw.delete_index_by_prefix(es_connection, app.config['ELASTIC_SEARCH_DB_PREFIX'])
        # else:
        #     return esprit.raw.delete_index(es_connection)
        print('Destroying indexes with prefix ' + app.config['ELASTIC_SEARCH_DB_PREFIX'] + '*')
        return ES.indices.delete(app.config['ELASTIC_SEARCH_DB_PREFIX'] + '*')

    @classmethod
    def check_es_raw_response(cls, res, extra_trace_info=''):
        if 'error' in res:
            es_resp = json.dumps(res, indent=2)

            error_to_raise = ESMappingMissingError if ES_MAPPING_MISSING_REGEX.match(es_resp) else ESError

            raise error_to_raise(
                (
                    "Elasticsearch returned an error:"
                    "\nES HTTP Response status: {es_status}"
                    "\nES Response:{es_resp}"
                    .format(es_status=res.get('status', 'unknown'), es_resp=es_resp)
                ) + extra_trace_info
            )

        if 'hits' not in res and 'hits' not in res['hits']:  # i.e. if res['hits']['hits'] does not exist
            raise ESResponseCannotBeInterpreted(
                (
                    "Elasticsearch did not return any records. "
                    "It probably returned an error we did not understand instead."
                    "\nES HTTP Response status: {es_status}"
                    "\nES Response:{es_resp}\n"
                    .format(es_status=res.get('status', 'unknown'), es_resp=json.dumps(res, indent=2))
                    ) + extra_trace_info
            )
        return True

    @classmethod
    def handle_es_raw_response(cls, res, wrap, extra_trace_info=''):
        """
        Handles the JSON returned by ES, raising errors as needed. If no problems are detected it returns its input
        unchanged.

        :param res: The full ES raw response to a query in a Python dict (this method does not handle the raw JSON ES
        outputs). Usually this parameter is the return value of the .query or .send_query methods.
        :param wrap: Did the caller request wrapping of each ES record inside a model object? This matters for handling
        records that have no '_source' or 'fields' keys, but do have an '_id' key. Such records should raise an error
        if wrapping was requested, since there is nothing to wrap. If no wrapping was requested, perhaps the caller
        simply needed the object IDs and nothing else, so we do not need to raise an error.
        :param extra_trace_info: A string with additional diagnostic information to be put into exceptions.
        """

        cls.check_es_raw_response(res)

        rs = []
        for i, each in enumerate(res['hits']['hits']):
            if '_source' in each:
                rs.append(each['_source'])
            elif 'fields' in each:
                rs.append(each['fields'])
            elif '_id' in each and not wrap:
                # "_id" is a sibling (not child) of "_source" so it can only be used with unwrapped raw responses.
                # wrap = True only makes sense if "_source" or "fields" were returned.
                # So, if "_id" is the only one present, extract it into an object that's shaped the same as the item
                # in the raw response.
                rs.append({"_id": each['_id']})
            else:
                msg1 = "Can't find any useful data in the ES response.\n" + extra_trace_info
                msg2 = "\nItem {i}.\nItem data:\n{each}".format(i=i, each=json.dumps(each, indent=2))
                raise ESResponseCannotBeInterpreted(msg1 + msg2)

        return rs

    @classmethod
    def iterate(cls, q, page_size=1000, limit=None, wrap=True):
        theq = deepcopy(q)
        theq["size"] = page_size
        theq["from"] = 0
        if "sort" not in theq:             # to ensure complete coverage on a changing index, sort by id is our best bet
            theq["sort"] = [{"_id": {"order": "asc"}}]
        counter = 0
        while True:
            # apply the limit
            if limit is not None and counter >= limit:
                break
            
            res = cls.query(q=theq)
            rs = cls.handle_es_raw_response(
                res,
                wrap=wrap,
                extra_trace_info=
                    "\nQuery sent to ES:\n{q}\n"
                    "\n\nPage #{counter} of the ES response with size {page_size}."
                    .format(q=json.dumps(theq, indent=2), counter=counter, page_size=page_size)
            )

            if len(rs) == 0:
                break
            for r in rs:
                # apply the limit (again)
                if limit is not None and counter >= limit:
                    break
                counter += 1
                if wrap:
                    yield cls(**r)
                else:
                    yield r
            theq["from"] += page_size   
    
    @classmethod
    def iterall(cls, page_size=1000, limit=None):
        return cls.iterate(MatchAllQuery().query(), page_size, limit)

    @classmethod
    def prefix_query(cls, field, prefix, size=5, facet_field=None, analyzed_field=True):
        # example of a prefix query
        # {
        #     "query": {"prefix" : { "bibjson.publisher" : "ope" } },
        #     "size": 0,
        #     "facets" : {
        #       "publisher" : { "terms" : {"field" : "bibjson.publisher.exact", "size": 5} }
        #     }
        # }

        suffix = app.config['FACET_FIELD']
        query_field = field
        if analyzed_field:
            if field.endswith(suffix):
                # strip .exact (or whatever it's configured as) off the end
                query_field = field[:field.rfind(suffix)]
        else:
            if not field.endswith(suffix):
                query_field = field + suffix

        # the actual terms should come from the .exact version of the
        # field - we are suggesting whole values, not fragments
        if facet_field is None:
            facet_field = query_field + suffix
        if not facet_field.endswith(suffix):
            facet_field = facet_field + suffix

        q = PrefixAutocompleteQuery(query_field, prefix, field, facet_field, size)
        return cls.send_query(q.query())

    @classmethod
    def wildcard_autocomplete_query(cls, field, substring, before=True, after=True, facet_size=5, facet_field=None):
        """
        Example of a wildcard query
        Works only on .exact fields

        {
            "query" : {
                "wildcard" : {"bibjson.publisher.exact" : "De *"}
            },
            "size" : 0,
            "facets" : {
                "bibjson.publisher.exact" : {
                    "terms" : {"field" : "bibjson.publisher.exact", "size" : 5}
                }
            }
        }
        :param field:
        :param substring:
        :param facet_size:
        :return:
        """
        # wildcard queries need to be on unanalyzed fields
        suffix = app.config['FACET_FIELD']
        filter_field = field
        if not filter_field.endswith(suffix):
            filter_field = filter_field + suffix

        # add the wildcard before/after
        if before:
            substring = "*" + substring
        if after:
            substring = substring + "*"

        # sort out the facet field
        if facet_field is None:
            facet_field = filter_field
        if not facet_field.endswith(suffix):
            facet_field = facet_field + suffix

        # build the query
        q = WildcardAutocompleteQuery(filter_field, substring, field, facet_field, facet_size)
        return cls.send_query(q)

    @classmethod
    def advanced_autocomplete(cls, filter_field, facet_field, substring, size=5, prefix_only=True):
        analyzed = True
        if " " in substring:
            analyzed = False

        substring = substring.lower()

        if " " in substring and not prefix_only:
            res = cls.wildcard_autocomplete_query(filter_field, substring, before=True, after=True, facet_size=size, facet_field=facet_field)
        else:
            res = cls.prefix_query(filter_field, substring, size=size, facet_field=facet_field, analyzed_field=analyzed)

        result = []
        for term in res['aggs'][filter_field]['terms']:
            # keep ordering - it's by count by default, so most frequent
            # terms will now go to the front of the result list
            result.append({"id": term['term'], "text": term['term']})
        return result

    @classmethod
    def autocomplete(cls, field, prefix, size=5):
        res = None
        # if there is a space in the prefix, the prefix query won't work, so we fall back to a wildcard
        # we only do this if we have to, because the wildcard query is a little expensive
        if " " in prefix:
            res = cls.wildcard_autocomplete_query(field, prefix, before=False, after=True, facet_size=size)
        else:
            prefix = prefix.lower()
            res = cls.prefix_query(field, prefix, size=size)

        result = []
        for term in res['aggs'][field]['terms']:
            # keep ordering - it's by count by default, so most frequent
            # terms will now go to the front of the result list
            result.append({"id": term['term'], "text": term['term']})
        return result

    @classmethod
    def q2obj(cls, **kwargs):
        extra_trace_info = ''
        if 'q' in kwargs:
            extra_trace_info = "\nQuery sent to ES (before manipulation in DomainObject.query):\n{}\n".format(json.dumps(kwargs['q'], indent=2))

        res = cls.query(**kwargs)
        rs = cls.handle_es_raw_response(res, wrap=True, extra_trace_info=extra_trace_info)
        results = [cls(**r) for r in rs]
        return results

    @classmethod
    def all(cls, size=10000, **kwargs):
        """ This is a shortcut to a match_all query with a large size, to return all records """
        # FIXME: is this only used in tests? ES now limits size so we can't guarantee ALL without using scroll / scan
        return cls.q2obj(size=size, **kwargs)

    @classmethod
    def count(cls):
        res = ES.count(index=cls.index_name(), doc_type=cls.doc_type())
        return res.get("count")
        # return requests.get(cls.target() + '_count').json()['count']

    @classmethod
    def hit_count(cls, query, **kwargs):
        countable_query = deepcopy(query)
        if "track_total_hits" not in countable_query:
            countable_query["track_total_hits"] = True

        res = cls.query(q=countable_query, **kwargs)
        return res.get("hits", {}).get("total", {}).get("value", 0)

    @classmethod
    def block(cls, id, last_updated, sleep=0.5, max_retry_seconds=30):
        threshold = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%SZ")
        q = BlockQuery(id)
        start_time = datetime.now()
        while True:
            res = cls.query(q=q.query())
            hits = res.get("hits", {}).get("hits", [])
            if len(hits) > 0:
                obj = hits[0].get("fields")
                if "last_updated" in obj:
                    lu = obj["last_updated"]
                    if len(lu) > 0:
                        lud = datetime.strptime(lu[0], "%Y-%m-%dT%H:%M:%SZ")
                        if lud >= threshold:
                            return
            else:
                if (datetime.now() - start_time).total_seconds() >= max_retry_seconds:
                    raise BlockTimeOutException("Attempting to block until record with id {id} appears in Elasticsearch, but this has not happened after {limit}".format(id=id, limit=max_retry_seconds))

            time.sleep(sleep)

    @classmethod
    def blockall(cls, ids_and_last_updateds, sleep=0.05, individual_max_retry_seconds=30):
        for id, lu in ids_and_last_updateds:
            cls.block(id, lu, sleep=sleep, max_retry_seconds=individual_max_retry_seconds)

    @classmethod
    def blockdeleted(cls, id, sleep=0.5, max_retry_seconds=30):
        q = BlockQuery(id)
        start_time = datetime.now()
        while True:
            res = cls.query(q=q.query())
            hits = res.get("hits", {}).get("hits", [])
            if len(hits) == 0:
                return
            else:
                if (datetime.now() - start_time).total_seconds() >= max_retry_seconds:
                    raise BlockTimeOutException(
                        "Attempting to block until record with id {id} deleted from Elasticsearch, but this has not happened after {limit}".format(
                            id=id, limit=max_retry_seconds))

            time.sleep(sleep)

    @classmethod
    def blockalldeleted(cls, ids, sleep=0.05, individual_max_retry_seconds=30):
        for id in ids:
            cls.blockdeleted(id, sleep, individual_max_retry_seconds)


class BlockTimeOutException(Exception):
    pass


class DAOSaveExceptionMaxRetriesReached(Exception):
    pass


class ESResponseCannotBeInterpreted(Exception):
    pass


class ESMappingMissingError(Exception):
    pass


class ESError(Exception):
    pass

########################################################################
# Some useful ES queries
########################################################################


class MatchAllQuery(object):
    def query(self):
        return {
            "track_total_hits" : True,
            "query": {
                "match_all": {}
            }
        }


class BlockQuery(object):
    def __init__(self, id):
        self._id = id

    def query(self):
        return {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"id.exact": self._id}}
                    ]
                }
            },
            "_source" : False,
            "docvalue_fields": [
                {"field": "last_updated", "format": "date_time_no_millis"}
            ]
        }


class PrefixAutocompleteQuery(object):
    def __init__(self, query_field, prefix, agg_name, agg_field, agg_size):
        self._query_field = query_field
        self._prefix = prefix
        self._agg_name = agg_name
        self._agg_field = agg_field
        self._agg_size = agg_size

    def query(self):
        return {
            "track_total_hits": True,
            "query": {"prefix": {self._query_field: self._prefix.lower()}},
            "size": 0,
            "aggs": {
                self._agg_name: {"terms": {"field": self._agg_field, "size": self._agg_size}}
            }
        }

class WildcardAutocompleteQuery(object):
    def __init__(self, wildcard_field, wildcard_query, agg_name, agg_field, agg_size):
        self._wildcard_field = wildcard_field
        self._wildcard_query = wildcard_query
        self._agg_name = agg_name
        self._agg_field = agg_field
        self._agg_size = agg_size

    def query(self):
        return {
            "track_total_hits": True,
            "query": {
                "wildcard": {self._wildcard_field: self._wildcard_query}
            },
            "size": 0,
            "aggs": {
                self._agg_name: {
                    "terms": {"field": self._agg_field, "size": self._agg_size}
                }
            }
        }


#########################################################################
# A query handler that knows how to speak facetview2
#########################################################################


class Facetview2(object):
    """
    ~~SearchURLGenerator:Feature->Elasticsearch:Technology~~
    """

    # Examples of queries
    # {"query":{"filtered":{"filter":{"bool":{"must":[{"term":{"_type":"article"}}]}},"query":{"query_string":{"query":"richard","default_operator":"OR"}}}},"from":0,"size":10}
    # {"query":{"query_string":{"query":"richard","default_operator":"OR"}},"from":0,"size":10}

    @staticmethod
    def make_term_filter(term, value):
        return {"term": {term: value}}

    @staticmethod
    def make_query(query_string=None, filters=None, default_operator="OR", sort_parameter=None, sort_order="asc", default_field=None):
        query_part = {"match_all": {}}
        if query_string is not None:
            query_part = {"query_string": {"query": query_string, "default_operator": default_operator}}
            if default_field is not None:
                query_part["query_string"]["default_field"] = default_field
        query = {"query": query_part}

        if filters is not None:
            if not isinstance(filters, list):
                filters = [filters]
            filters.append(query_part)
            bool_part = {"bool": {"must": filters}}
            query = {"query": query_part}

        if sort_parameter is not None:
            # For facetview we can only have one sort parameter, but ES actually supports lists
            sort_part = [{sort_parameter: {"order": sort_order}}]
            query["sort"] = sort_part

        return query

    @staticmethod
    def url_encode_query(query):
        return urllib.parse.quote(json.dumps(query).replace(' ', ''))

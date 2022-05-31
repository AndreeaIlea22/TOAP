from portality.lib.argvalidate import argvalidate
from portality import models
from portality.bll import exceptions
from portality import constants

class TodoService(object):
    """
    ~~Todo:Service->DOAJ:Service~~
    """

    def top_todo(self, account, size=25):
        """
        Returns the top number of todo items for a given user

        :param account:
        :return:
        """
        # first validate the incoming arguments to ensure that we've got the right thing
        argvalidate("top_todo", [
            {"arg" : account, "instance" : models.Account, "allow_none" : False, "arg_name" : "account"}
        ], exceptions.ArgumentException)


        queries = []
        if account.has_role("admin"):
            maned_of = [g for g in models.EditorGroup.groups_by_maned(account.id)]
            queries.append(TodoRules.maned_stalled(size, maned_of))
            queries.append(TodoRules.maned_follow_up_old(size, maned_of))
            queries.append(TodoRules.maned_ready(size, maned_of))
            queries.append(TodoRules.maned_completed(size, maned_of))
            queries.append(TodoRules.maned_assign_pending(size, maned_of))

        todos = []
        for aid, q, sort, boost in queries:
            applications = models.Application.object_query(q=q.query())
            for ap in applications:
                todos.append({
                    "date": ap.last_manual_update_timestamp if sort == "last_manual_update" else ap.created_timestamp,
                    "date_type": sort,
                    "action_id" : [aid],
                    "title" : ap.bibjson().title,
                    "object_id" : ap.id,
                    "object" : ap,
                    "boost": boost
                })

        todos = self._rationalise_todos(todos, size)

        return todos

    def _rationalise_todos(self, todos, size):
        boosted = list(filter(lambda x: x["boost"], todos))
        unboosted = list(filter(lambda x: not x["boost"], todos))

        stds = sorted(boosted, key=lambda x: x['date']) + sorted(unboosted, key=lambda x: x['date'])

        id_map = {}
        removals = []
        for i in range(len(stds)):
            todo = stds[i]
            oid = todo["object_id"]
            if oid in id_map:
                removals.append(i)
                stds[id_map[oid]]['action_id'] += todo['action_id']
            else:
                id_map[oid] = i

        removals.reverse()
        for r in removals:
            del stds[r]

        return stds[:size]


class TodoRules(object):
    @classmethod
    def maned_stalled(cls, size, maned_of):
        stalled = TodoQuery(
            musts=[
                TodoQuery.lmu_older_than(8),
                TodoQuery.editor_group(maned_of)
            ],
            must_nots=[
                TodoQuery.status([constants.APPLICATION_STATUS_ACCEPTED, constants.APPLICATION_STATUS_REJECTED])
            ],
            sort="last_manual_update",
            size=size
        )
        return constants.TODO_MANED_STALLED, stalled, "last_manual_update", False

    @classmethod
    def maned_follow_up_old(cls, size, maned_of):
        follow_up_old = TodoQuery(
            musts=[
                TodoQuery.cd_older_than(10),
                TodoQuery.editor_group(maned_of)
            ],
            must_nots=[
                TodoQuery.status([constants.APPLICATION_STATUS_ACCEPTED, constants.APPLICATION_STATUS_REJECTED])
            ],
            sort="created_date",
            size=size
        )
        return constants.TODO_MANED_FOLLOW_UP_OLD, follow_up_old, "created_date", False

    @classmethod
    def maned_ready(cls, size, maned_of):
        ready = TodoQuery(
            musts=[
                TodoQuery.status([constants.APPLICATION_STATUS_READY]),
                TodoQuery.editor_group(maned_of)
            ],
            sort="last_manual_update",
            size=size
        )
        return constants.TODO_MANED_READY, ready, "last_manual_update", True

    @classmethod
    def maned_completed(cls, size, maned_of):
        completed = TodoQuery(
            musts=[
                TodoQuery.status([constants.APPLICATION_STATUS_COMPLETED]),
                TodoQuery.lmu_older_than(2),
                TodoQuery.editor_group(maned_of)
            ],
            sort="last_manual_update",
            size=size
        )
        return constants.TODO_MANED_COMPLETED, completed, "last_manual_update", False

    @classmethod
    def maned_assign_pending(cls, size, maned_of):
        assign_pending = TodoQuery(
            musts=[
                TodoQuery.exists("admin.editor_group"),
                TodoQuery.lmu_older_than(2),
                TodoQuery.status([constants.APPLICATION_STATUS_PENDING]),
                TodoQuery.editor_group(maned_of)
            ],
            must_nots=[
                TodoQuery.exists("admin.editor")
            ],
            sort="created_date",
            size=size
        )
        return constants.TODO_MANED_ASSIGN_PENDING, assign_pending, "last_manual_update", False


class TodoQuery(object):
    """
    ~~->$Todo:Query~~
    ~~^->Elasticsearch:Technology~~
    """
    lmu_sort = {"last_manual_update" : {"order" : "asc"}}
    cd_sort = {"created_date" : {"order" : "asc"}}

    def __init__(self, musts=None, must_nots=None, sort="last_manual_update", size=10):
        self._musts = [] if musts is None else musts
        self._must_nots = [] if must_nots is None else must_nots
        self._sort = sort
        self._size = size

    def query(self):
        sort = self.lmu_sort if self._sort == "last_manual_update" else self.cd_sort
        q = {
            "query" : {
                "bool" : {
                    "must": self._musts,
                    "must_not": self._must_nots
                }
            },
            "sort" : [
                sort
            ],
            "size" : self._size
        }
        return q

    @classmethod
    def editor_group(cls, groups):
        return {
            "terms" : {
                "admin.editor_group.exact" : [g.name for g in groups]
            }
        }

    @classmethod
    def lmu_older_than(cls, weeks):
        return {
            "range": {
                "last_manual_update": {
                    "lte": "now-" + str(weeks) + "w"
                }
            }
        }

    @classmethod
    def cd_older_than(cls, weeks):
        return {
            "range": {
                "created_date": {
                    "lte": "now-" + str(weeks) + "w"
                }
            }
        }

    @classmethod
    def status(cls, statuses):
        return {
            "terms" : {
                "admin.application_status.exact" : statuses
            }
        }

    @classmethod
    def exists(cls, field):
        return {
            "exists" : {
                "field" : field
            }
        }
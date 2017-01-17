from flask_login import current_user
from portality import models, lock
from portality.core import app

from portality.tasks.redis_huey import main_queue
from portality.decorators import write_required

from portality.background import BackgroundTask, BackgroundApi

def change_by_query(query, in_doaj_new_val, dry_run=True):
    ids = []
    sane = {}
    sane["query"] = query["query"]
    for j in models.Journal.iterate(sane, wrap=False):
        ids.append(j.get("id"))
    if not dry_run:
        change_in_doaj(ids, in_doaj_new_val, selection_query=sane)
    return len(ids)

def change_in_doaj(journal_ids, in_doaj_new_val, **kwargs):
    job = SetInDOAJBackgroundTask.prepare(current_user.id, journal_ids=journal_ids, in_doaj=in_doaj_new_val, **kwargs)
    SetInDOAJBackgroundTask.submit(job)


class SetInDOAJBackgroundTask(BackgroundTask):

    __action__ = "set_in_doaj"

    def run(self):
        """
        Execute the task as specified by the background_jon
        :return:
        """
        job = self.background_job
        params = job.params

        journal_ids = params.get("set_in_doaj__journal_ids")
        in_doaj = params.get("set_in_doaj__in_doaj")

        if journal_ids is None or len(journal_ids) == 0 or in_doaj is None:
            raise RuntimeError(u"SetInDOAJBackgroundTask.run run without sufficient parameters")

        for journal_id in journal_ids:
            job.add_audit_message(u"Setting in_doaj to {x} for journal {y}".format(x=str(in_doaj), y=journal_id))

            j = models.Journal.pull(journal_id)
            if j is None:
                raise RuntimeError(u"Journal with id {} does not exist".format(journal_id))
            j.bibjson().active = in_doaj
            j.set_in_doaj(in_doaj)
            j.save()
            j.propagate_in_doaj_status_to_articles()  # will save each article, could take a while
            job.add_audit_message(u"Journal {x} set in_doaj to {y}, and all associated articles".format(x=journal_id, y=str(in_doaj)))

    def cleanup(self):
        """
        Cleanup after a successful OR failed run of the task
        :return:
        """
        # remove the lock on the journal
        job = self.background_job
        params = job.params
        journal_ids = params.get("set_in_doaj__journal_ids")
        username = job.user

        lock.batch_unlock("journal", journal_ids, username)

    @classmethod
    def prepare(cls, username, **kwargs):
        """
        Take an arbitrary set of keyword arguments and return an instance of a BackgroundJob,
        or fail with a suitable exception

        :param kwargs: arbitrary keyword arguments pertaining to this task type
        :return: a BackgroundJob instance representing this task
        """

        # first prepare a job record
        job = models.BackgroundJob()
        job.user = username
        job.action = cls.__action__

        journal_ids = kwargs.get("journal_ids")

        params = {}
        params["set_in_doaj__journal_ids"] = journal_ids
        params["set_in_doaj__in_doaj"] = kwargs.get("in_doaj")

        if params["set_in_doaj__journal_ids"] is None or params["set_in_doaj__in_doaj"] is None:
            raise RuntimeError(u"SetInDOAJBackgroundTask.prepare run without sufficient parameters")

        job.params = params

        if "selection_query" in kwargs:
            job.reference = {'set_in_doaj__selection_query': kwargs.get('selection_query')}

        # now ensure that we have the locks for this journal
        # will raise an exception if this fails
        lock.batch_lock("journal", journal_ids, username, timeout=app.config.get("BACKGROUND_TASK_LOCK_TIMEOUT", 3600))

        return job

    @classmethod
    def submit(cls, background_job):
        """
        Submit the specified BackgroundJob to the background queue

        :param background_job: the BackgroundJob instance
        :return:
        """
        background_job.save()
        set_in_doaj.schedule(args=(background_job.id,), delay=10)

@main_queue.task()
@write_required(script=True)
def set_in_doaj(job_id):
    job = models.BackgroundJob.pull(job_id)
    task = SetInDOAJBackgroundTask(job)
    BackgroundApi.execute(task)

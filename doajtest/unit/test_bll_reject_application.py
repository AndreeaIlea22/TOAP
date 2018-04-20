import time

from parameterized import parameterized

from portality import constants
from doajtest.fixtures import ApplicationFixtureFactory, AccountFixtureFactory, JournalFixtureFactory
from doajtest.helpers import DoajTestCase, load_from_matrix
from portality.bll import DOAJ
from portality.bll import exceptions
from portality.models import Account, Suggestion, Provenance, Journal


def load_test_cases():
    return load_from_matrix("reject_application.csv", test_ids=[])


def mock_save_fail(*args, **kwargs):
    return None


EXCEPTIONS = {
    "ArgumentException" : exceptions.ArgumentException,
    "SaveException" : exceptions.SaveException,
    "AuthoriseException" : exceptions.AuthoriseException
}


class TestBLRejectApplication(DoajTestCase):

    def setUp(self):
        super(TestBLRejectApplication, self).setUp()
        self.old_save = Suggestion.save

    def tearDown(self):
        super(TestBLRejectApplication, self).tearDown()
        Suggestion.save = self.old_save

    @parameterized.expand(load_test_cases)
    def test_01_reject_application(self, name, application, application_status, account, prov, current_journal, save, raises=None):

        #######################################
        ## set up

        if save == "fail":
            Suggestion.save = mock_save_fail

        ap = None
        journal = None
        if application == "exists":
            ap = Suggestion(**ApplicationFixtureFactory.make_application_source())
            ap.set_application_status(application_status)
            ap.set_id(ap.makeid())
            if current_journal == "yes":
                journal = Journal(**JournalFixtureFactory.make_journal_source(in_doaj=True))
                journal.set_id(journal.makeid())
                journal.set_current_application(ap.id)
                journal.save(blocking=True)
                ap.set_current_journal(journal.id)

        acc = None
        if account == "publisher":
            acc = Account(**AccountFixtureFactory.make_publisher_source())
        elif account == "admin":
            acc = Account(**AccountFixtureFactory.make_managing_editor_source())

        provenance = None
        if prov != "none":
            provenance = prov == "true"

        ########################################
        ## execute

        svc = DOAJ.applicationService()
        if raises is not None and raises != "":
            with self.assertRaises(EXCEPTIONS[raises]):
                svc.reject_application(ap, acc, provenance)
        else:
            svc.reject_application(ap, acc, provenance)
            time.sleep(1)

            #######################################
            ## Check

            ap2 = Suggestion.pull(ap.id)
            assert ap2 is not None
            assert ap2.application_status == constants.APPLICATION_STATUS_REJECTED
            assert ap2.current_journal is None

            if current_journal == "yes" and journal is not None:
                j2 = Journal.pull(journal.id)
                assert j2 is not None
                assert j2.current_application is None
                assert ap2.related_journal == j2.id

            if prov == "true":
                pr = Provenance.get_latest_by_resource_id(ap.id)
                assert pr is not None
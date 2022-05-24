from portality import models
from portality import constants
from portality.bll import exceptions
from doajtest.helpers import DoajTestCase
from portality.events.consumers.application_publisher_rejected_notify import ApplicationPublisherRejectedNotify
from doajtest.fixtures import ApplicationFixtureFactory
import time


class TestApplicationPublisherRejectedNotify(DoajTestCase):
    def setUp(self):
        super(TestApplicationPublisherRejectedNotify, self).setUp()

    def tearDown(self):
        super(TestApplicationPublisherRejectedNotify, self).tearDown()

    def test_consumes(self):

        event = models.Event(constants.EVENT_APPLICATION_STATUS, context={"application" : {}, "old_status" : "in progress", "new_status": "rejected"})
        assert ApplicationPublisherRejectedNotify.consumes(event)

        event = models.Event(constants.EVENT_APPLICATION_STATUS,
                             context={"old_status": "rejected", "new_status": "rejected"})
        assert not ApplicationPublisherRejectedNotify.consumes(event)

        event = models.Event("test:event", context={"application" : "2345"})
        assert not ApplicationPublisherRejectedNotify.consumes(event)

        event = models.Event(constants.EVENT_APPLICATION_STATUS)
        assert not ApplicationPublisherRejectedNotify.consumes(event)

    def test_consume_success(self):
        self._make_and_push_test_context("/")

        acc = models.Account()
        acc.set_id("publisher")
        acc.set_email("test@example.com")
        acc.save(blocking=True)

        source = ApplicationFixtureFactory.make_application_source()

        event = models.Event(constants.EVENT_APPLICATION_STATUS, context={"application" : source, "old_status": "in progress", "new_status": "rejected"})
        ApplicationPublisherRejectedNotify.consume(event)

        time.sleep(2)
        ns = models.Notification.all()
        assert len(ns) == 1

        n = ns[0]
        assert n.who == "publisher"
        assert n.created_by == ApplicationPublisherRejectedNotify.ID
        assert n.classification == constants.NOTIFICATION_CLASSIFICATION_STATUS_CHANGE
        assert n.message is not None
        assert not n.is_seen()

    def test_consume_fail(self):
        event = models.Event(constants.EVENT_APPLICATION_STATUS, context={"application": {"key" : "value"}})
        with self.assertRaises(exceptions.NoSuchObjectException):
            ApplicationPublisherRejectedNotify.consume(event)


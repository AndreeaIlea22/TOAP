from portality.core import app
from portality.lib import plugin

from portality.events.consumers.account_created_email import AccountCreatedEmail
from portality.events.consumers.application_assed_inprogress_notify import ApplicationAssedInprogressNotify
from portality.events.consumers.application_assed_assigned_notify import ApplicationAssedAssignedNotify
from portality.events.consumers.application_maned_ready_notify import ApplicationManedReadyNotify
from portality.events.consumers.application_editor_completed_notify import ApplicationEditorCompletedNotify


class EventsService(object):
    EVENT_CONSUMERS = [
        AccountCreatedEmail,
        ApplicationAssedInprogressNotify,
        ApplicationAssedAssignedNotify,
        ApplicationManedReadyNotify,
        ApplicationEditorCompletedNotify
    ]

    def __init__(self):
        self.trigger_function = plugin.load_function(app.config.get("EVENT_SEND_FUNCTION"))

    def trigger(self, event):
        self.trigger_function(event)

    def consume(self, event):
        for consumer in self.EVENT_CONSUMERS:
            try:
                if consumer.consumes(event):
                    consumer.consume(event)
            except Exception as e:
                app.logger.error(str(e))

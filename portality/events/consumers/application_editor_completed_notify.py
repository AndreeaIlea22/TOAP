from flask import url_for

from portality.events.consumer import EventConsumer
from portality import constants
from portality import models
from portality.lib import edges
from portality.bll import DOAJ, exceptions


class ApplicationEditorCompletedNotify(EventConsumer):
    ID = "application:editor:completed:notify"

    @classmethod
    def consumes(cls, event):
        return event.id == constants.EVENT_APPLICATION_STATUS and \
                event.context.get("old_status") != constants.APPLICATION_STATUS_COMPLETED and \
                event.context.get("new_status") == constants.APPLICATION_STATUS_COMPLETED

    @classmethod
    def consume(cls, event):
        context = event.context
        app_id = context.get("application")
        if app_id is None:
            return
        application = models.Application.pull(app_id)
        if application is None:
            raise exceptions.NoSuchObjectException("Unable to locate application with id {x}".format(x=app_id))

        if not application.editor_group:
            return

        associate_editor = "unknown associate editor"
        if application.editor:
            associate_editor = application.editor

        # Notification is to the editor in charge of this application's assigned editor group
        editor_group_name = application.editor_group
        editor_group_id = models.EditorGroup.group_exists_by_name(name=editor_group_name)
        eg = models.EditorGroup.pull(editor_group_id)
        group_editor = eg.editor

        if not group_editor:
            return

        svc = DOAJ.notificationsService()

        notification = models.Notification()
        notification.who = group_editor
        notification.created_by = cls.ID
        notification.classification = constants.NOTIFICATION_CLASSIFICATION_STATUS_CHANGE
        notification.message = svc.message(cls.ID).format(
            application_title=application.bibjson().title,
            associate_editor=associate_editor
        )

        string_id_query = edges.make_url_query(query_string=application.id)
        notification.action = url_for("editor.group_suggestions", source=string_id_query)

        svc.notify(notification)

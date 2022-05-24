# ~~ Email:Notifications~~
from flask import url_for
import json

from portality import models, app_email, constants
from portality.core import app
from portality.dao import Facetview2
from portality.ui.messages import Messages
from portality.lib import dates


def send_editor_completed_email(application):
    """ inform the editor in charge of an application that it has been completed by an associate editor """
    journal_name = application.bibjson().title
    url_root = app.config.get("BASE_URL")
    query_for_id = Facetview2.make_query(query_string=application.id)
    string_id_query = json.dumps(query_for_id).replace(' ', '')       # Avoid '+' being added to URLs by removing spaces
    url_for_application = url_root + url_for("editor.group_suggestions", source=string_id_query)

    # This is to the editor in charge of this application's assigned editor group
    editor_group_name = application.editor_group
    editor_group_id = models.EditorGroup.group_exists_by_name(name=editor_group_name)
    editor_group = models.EditorGroup.pull(editor_group_id)
    editor_acc = editor_group.get_editor_account()

    editor_id = editor_acc.id
    to = [editor_acc.email]
    fro = app.config.get('SYSTEM_EMAIL_FROM', 'helpdesk@doaj.org')
    subject = app.config.get("SERVICE_NAME", "") + " - application marked 'completed'"

    # The status change will have come from the associate editor assigned to the journal
    assoc_id = application.editor

    app_email.send_mail(to=to,
                        fro=fro,
                        subject=subject,
                        template_name="email/editor_application_completed.jinja2",
                        editor=editor_id,
                        associate_editor=assoc_id,
                        application_title=journal_name,
                        url_for_application=url_for_application)


def send_publisher_reject_email(application, note=None, update_request=False):
    """Tell the publisher their application was rejected"""
    send_instructions = []

    owner = models.Account.pull(application.owner)
    if owner is not None:
        send_instructions.append({
            "owner" : owner,
            "name" : owner.name,
            "email" : owner.email,
            "type" : "owner"
        })

    if len(send_instructions) == 0:
        raise app_email.EmailException("Application {x} does not have an owner or suggester, cannot send email".format(x=application.id))

    # determine if this is an application or an update request
    app_type = "application" if update_request is False else "update"

    for instructions in send_instructions:
        to = [instructions["email"]]
        fro = app.config.get('SYSTEM_EMAIL_FROM', 'helpdesk@doaj.org')
        subject = app.config.get("SERVICE_NAME", "") + " - your " + app_type + " was rejected"

        if update_request:
            app_email.send_mail(to=to,
                                fro=fro,
                                subject=subject,
                                template_name="email/publisher_update_request_rejected.jinja2",
                                owner=instructions["owner"],
                                application=application,
                                note=note)
        else:
            app_email.send_mail(to=to,
                                fro=fro,
                                subject=subject,
                                template_name="email/publisher_application_rejected.jinja2",
                                owner=instructions["owner"],
                                application=application,
                                note=note)

    return send_instructions


def send_account_created_email(account):
    reset_url = url_for('account.reset', reset_token=account.reset_token, _external=True)
    forgot_pw_url = url_for('account.forgot', _external=True)

    password_create_timeout_seconds = int(
        app.config.get("PASSWORD_CREATE_TIMEOUT", app.config.get('PASSWORD_RESET_TIMEOUT', 86400) * 14))
    password_create_timeout_days = password_create_timeout_seconds / (60 * 60 * 24)

    to = [account.email]
    fro = app.config.get('SYSTEM_EMAIL_FROM', 'helpdesk@doaj.org')
    subject = app.config.get("SERVICE_NAME", "") + " - account created, please verify your email address"

    app_email.send_mail(to=to,
                        fro=fro,
                        subject=subject,
                        template_name="email/account_created.jinja2",
                        reset_url=reset_url,
                        email=account.email,
                        timeout_days=password_create_timeout_days,
                        forgot_pw_url=forgot_pw_url
                        )


def send_account_password_reset_email(account):
    reset_url = url_for('account.reset', reset_token=account.reset_token, _external=True)

    to = [account.email]
    fro = app.config.get('SYSTEM_EMAIL_FROM', app.config['ADMIN_EMAIL'])
    subject = app.config.get("SERVICE_NAME", "") + " - password reset"

    app_email.send_mail(to=to,
                        fro=fro,
                        subject=subject,
                        template_name="email/account_password_reset.jinja2",
                        email=account.email,
                        reset_url=reset_url,
                        forgot_pw_url=url_for('account.forgot', _external=True)
                        )

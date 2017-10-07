import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app as app

import requests

from nyaa import models


class EmailHolder(object):
    ''' Holds email subject, recipient and content, so we have a general class for
        all mail backends. '''

    def __init__(self, subject=None, recipient=None, text=None, html=None):
        self.subject = subject
        self.recipient = recipient  # models.User or string
        self.text = text
        self.html = html

    def format_recipient(self):
        if isinstance(self.recipient, models.User):
            return '{} <{}>'.format(self.recipient.username, self.recipient.email)
        else:
            return self.recipient

    def recipient_email(self):
        if isinstance(self.recipient, models.User):
            return self.recipient.email
        else:
            return self.recipient.email

    def as_mimemultipart(self):
        msg = MIMEMultipart()
        msg['Subject'] = self.subject
        msg['From'] = app.config['MAIL_FROM_ADDRESS']
        msg['To'] = self.format_recipient()

        msg.attach(MIMEText(self.text, 'plain'))
        if self.html:
            msg.attach(MIMEText(self.html, 'html'))

        return msg


def send_email(email_holder):
    mail_backend = app.config.get('MAIL_BACKEND')
    if mail_backend == 'mailgun':
        _send_mailgun(email_holder)
    elif mail_backend == 'smtp':
        _send_smtp(email_holder)
    elif mail_backend:
        # TODO: Do this in logging.error when we have that set up
        print('Unknown mail backend:', mail_backend)


def _send_mailgun(email_holder):
    mailgun_endpoint = app.config['MAILGUN_API_BASE'] + '/messages'
    auth = ('api', app.config['MAILGUN_API_KEY'])
    data = {
        'from': app.config['MAIL_FROM_ADDRESS'],
        'to': email_holder.format_recipient(),
        'subject': email_holder.subject,
        'text': email_holder.text,
        'html': email_holder.html
    }
    r = requests.post(mailgun_endpoint, data=data, auth=auth)
    # TODO real error handling?
    assert r.status_code == 200


def _send_smtp(email_holder):
    # NOTE: Unused, most likely untested! Should work, however.
    msg = email_holder.as_mimemultipart()

    server = smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'])
    server.set_debuglevel(1)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
    server.sendmail(app.config['SMTP_USERNAME'], email_holder.recipient_email(), msg.as_string())
    server.quit()

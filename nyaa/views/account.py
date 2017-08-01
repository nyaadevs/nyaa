import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ipaddress import ip_address

import flask

from nyaa import forms, models
from nyaa.extensions import db
from nyaa.views.users import get_activation_link

app = flask.current_app
bp = flask.Blueprint('account', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if flask.g.user:
        return flask.redirect(redirect_url())

    form = forms.LoginForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
        username = form.username.data.strip()
        password = form.password.data
        user = models.User.by_username(username)

        if not user:
            user = models.User.by_email(username)

        if (not user or password != user.password_hash or
                user.status == models.UserStatusType.INACTIVE):
            flask.flash(flask.Markup(
                '<strong>Login failed!</strong> Incorrect username or password.'), 'danger')
            return flask.redirect(flask.url_for('account.login'))

        user.last_login_date = datetime.utcnow()
        user.last_login_ip = ip_address(flask.request.remote_addr).packed
        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        flask.session['user_id'] = user.id
        flask.session.permanent = True
        flask.session.modified = True

        return flask.redirect(redirect_url())

    return flask.render_template('login.html', form=form)


@bp.route('/logout')
def logout():
    flask.g.user = None
    flask.session.permanent = False
    flask.session.modified = False

    response = flask.make_response(flask.redirect(redirect_url()))
    response.set_cookie(app.session_cookie_name, expires=0)
    return response


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if flask.g.user:
        return flask.redirect(redirect_url())

    form = forms.RegisterForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
        user = models.User(username=form.username.data.strip(),
                           email=form.email.data.strip(), password=form.password.data)
        user.last_login_ip = ip_address(flask.request.remote_addr).packed
        db.session.add(user)
        db.session.commit()

        if app.config['USE_EMAIL_VERIFICATION']:  # force verification, enable email
            activ_link = get_activation_link(user)
            send_verification_email(user.email, activ_link)
            return flask.render_template('waiting.html')
        else:  # disable verification, set user as active and auto log in
            user.status = models.UserStatusType.ACTIVE
            db.session.add(user)
            db.session.commit()
            flask.g.user = user
            flask.session['user_id'] = user.id
            flask.session.permanent = True
            flask.session.modified = True
            return flask.redirect(redirect_url())

    return flask.render_template('register.html', form=form)


@bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not flask.g.user:
        return flask.redirect('/')  # so we dont get stuck in infinite loop when signing out

    form = forms.ProfileForm(flask.request.form)

    if flask.request.method == 'POST' and form.validate():
        user = flask.g.user
        new_email = form.email.data.strip()
        new_password = form.new_password.data

        if new_email:
            # enforce password check on email change too
            if form.current_password.data != user.password_hash:
                flask.flash(flask.Markup(
                    '<strong>Email change failed!</strong> Incorrect password.'), 'danger')
                return flask.redirect('/profile')
            user.email = form.email.data
            flask.flash(flask.Markup(
                '<strong>Email successfully changed!</strong>'), 'success')
        if new_password:
            if form.current_password.data != user.password_hash:
                flask.flash(flask.Markup(
                    '<strong>Password change failed!</strong> Incorrect password.'), 'danger')
                return flask.redirect('/profile')
            user.password_hash = form.new_password.data
            flask.flash(flask.Markup(
                '<strong>Password successfully changed!</strong>'), 'success')

        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        return flask.redirect('/profile')

    return flask.render_template('profile.html', form=form)


def redirect_url():
    url = flask.request.args.get('next') or \
        flask.request.referrer or \
        '/'
    if url == flask.request.url:
        return '/'
    return url


def send_verification_email(to_address, activ_link):
    ''' this is until we have our own mail server, obviously.
     This can be greatly cut down if on same machine.
     probably can get rid of all but msg formatting/building,
     init line and sendmail line if local SMTP server '''

    msg_body = 'Please click on: ' + activ_link + ' to activate your account.\n\n\nUnsubscribe:'

    msg = MIMEMultipart()
    msg['Subject'] = 'Verification Link'
    msg['From'] = app.config['MAIL_FROM_ADDRESS']
    msg['To'] = to_address
    msg.attach(MIMEText(msg_body, 'plain'))

    server = smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'])
    server.set_debuglevel(1)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
    server.sendmail(app.config['SMTP_USERNAME'], to_address, msg.as_string())
    server.quit()

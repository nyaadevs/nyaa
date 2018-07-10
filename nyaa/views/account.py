import binascii
import time
from datetime import datetime
from ipaddress import ip_address

import flask

from nyaa import email, forms, models
from nyaa.extensions import db
from nyaa.utils import sha1_hash
from nyaa.views.users import get_activation_link, get_password_reset_link, get_serializer

app = flask.current_app
bp = flask.Blueprint('account', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if flask.g.user:
        return flask.redirect(redirect_url())

    form = forms.LoginForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
        if app.config['MAINTENANCE_MODE'] and not app.config['MAINTENANCE_MODE_LOGINS']:
            flask.flash(flask.Markup('<strong>Logins are currently disabled.</strong>'), 'danger')
            return flask.redirect(flask.url_for('account.login'))

        username = form.username.data.strip()
        password = form.password.data
        user = models.User.by_username(username)

        if not user:
            user = models.User.by_email(username)

        if not user or password != user.password_hash:
            flask.flash(flask.Markup(
                '<strong>Login failed!</strong> Incorrect username or password.'), 'danger')
            return flask.redirect(flask.url_for('account.login'))

        if user.is_banned:
            ban_reason = models.Ban.banned(user.id, None).first().reason
            ban_str = ('<strong>Login failed!</strong> You are banned with the '
                       'reason "{0}" If you believe that this is a mistake, contact '
                       'a moderator on IRC.'.format(ban_reason))
            flask.flash(flask.Markup(ban_str), 'danger')
            return flask.redirect(flask.url_for('account.login'))

        if user.status != models.UserStatusType.ACTIVE:
            flask.flash(flask.Markup(
                '<strong>Login failed!</strong> Account is not activated.'), 'danger')
            return flask.redirect(flask.url_for('account.login'))

        user.last_login_date = datetime.utcnow()
        user.last_login_ip = ip_address(flask.request.remote_addr).packed
        if not app.config['MAINTENANCE_MODE']:
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
        user.registration_ip = ip_address(flask.request.remote_addr).packed
        user.last_login_ip = user.registration_ip
        db.session.add(user)
        db.session.commit()
        if models.RangeBan.is_rangebanned(user.registration_ip):
            flask.flash(flask.Markup('Your IP is blocked from creating new accounts. '
                                     'Please <a href="{}">ask a moderator</a> to manually '
                                     'activate your account <a href="{}">\'{}\'</a>.'
                                     .format(flask.url_for('site.help') + '#irchelp',
                                             flask.url_for('users.view_user',
                                                           user_name=user.username),
                                             user.username)), 'warning')
        else:
            if app.config['USE_EMAIL_VERIFICATION']:  # force verification, enable email
                send_verification_email(user)
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


@bp.route('/password-reset/<payload>', methods=['GET', 'POST'])
@bp.route('/password-reset', methods=['GET', 'POST'])
def password_reset(payload=None):
    if not app.config['ALLOW_PASSWORD_RESET']:
        return flask.abort(404)

    if flask.g.user:
        return flask.redirect(redirect_url())

    if payload is None:
        form = forms.PasswordResetRequestForm(flask.request.form)
        if flask.request.method == 'POST' and form.validate():
            user = models.User.by_email(form.email.data.strip())
            if user:
                send_password_reset_request_email(user)

            flask.flash(flask.Markup(
                'A password reset request was sent to the provided email, '
                'if a matching account was found.'), 'info')
            return flask.redirect(flask.url_for('main.home'))
        return flask.render_template('password_reset_request.html', form=form)

    else:
        s = get_serializer()
        try:
            request_timestamp, pw_hash, user_id = s.loads(payload)
        except:
            return flask.abort(404)

        user = models.User.by_id(user_id)
        if not user:
            return flask.abort(404)

        # Timeout after six hours
        if (time.time() - request_timestamp) > 6 * 3600:
            return flask.abort(404)

        sha1_password_hash_hash = binascii.hexlify(sha1_hash(user.password_hash.hash)).decode()
        if pw_hash != sha1_password_hash_hash:
            return flask.abort(404)

        form = forms.PasswordResetForm(flask.request.form)
        if flask.request.method == 'POST' and form.validate():
            user.password_hash = form.password.data

            db.session.add(user)
            db.session.commit()

            send_password_reset_email(user)

            flask.flash(flask.Markup('Your password was reset. Log in now.'), 'info')
            return flask.redirect(flask.url_for('account.login'))
        return flask.render_template('password_reset.html', form=form)


@bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not flask.g.user:
        # so we don't get stuck in infinite loop when signing out
        return flask.redirect(flask.url_for('main.home'))

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
    home_url = flask.url_for('main.home')

    url = flask.request.args.get('next') or \
        flask.request.referrer or \
        home_url
    if url == flask.request.url:
        return home_url
    return url


def send_verification_email(user):
    activation_link = get_activation_link(user)

    tmpl_context = {
        'activation_link': activation_link,
        'user': user
    }

    email_msg = email.EmailHolder(
        subject='Verify your {} account'.format(app.config['GLOBAL_SITE_NAME']),
        recipient=user,
        text=flask.render_template('email/verify.txt', **tmpl_context),
        html=flask.render_template('email/verify.html', **tmpl_context),
    )

    email.send_email(email_msg)


def send_password_reset_email(user):
    ''' Alert user that their password has been successfully reset '''

    email_msg = email.EmailHolder(
        subject='Your {} password has been reset'.format(app.config['GLOBAL_SITE_NAME']),
        recipient=user,
        text=flask.render_template('email/reset.txt', user=user),
        html=flask.render_template('email/reset.html', user=user),
    )

    email.send_email(email_msg)


def send_password_reset_request_email(user):
    ''' Send user a password reset link '''
    reset_link = get_password_reset_link(user)

    tmpl_context = {
        'reset_link': reset_link,
        'user': user
    }

    email_msg = email.EmailHolder(
        subject='{} password reset request'.format(app.config['GLOBAL_SITE_NAME']),
        recipient=user,
        text=flask.render_template('email/reset-request.txt', **tmpl_context),
        html=flask.render_template('email/reset-request.html', **tmpl_context),
    )

    email.send_email(email_msg)

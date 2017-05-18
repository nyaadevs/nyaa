import flask
from werkzeug.datastructures import CombinedMultiDict
from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, utils
from nyaa import torrents
from nyaa import backend
from nyaa import api_handler
from nyaa.search import search_elastic, search_db
import config

import json
from datetime import datetime, timedelta
import ipaddress
import os.path
import base64
from urllib.parse import quote
import math
from werkzeug import url_encode

from itsdangerous import URLSafeSerializer, BadSignature

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

from flask_paginate import Pagination


DEBUG_API = False
DEFAULT_MAX_SEARCH_RESULT = 1000
DEFAULT_PER_PAGE = 75
SERACH_PAGINATE_DISPLAY_MSG = ('Displaying results {start}-{end} out of {total} results.<br>\n'
                               'Please refine your search results if you can\'t find '
                               'what you were looking for.')


def redirect_url():
    url = flask.request.args.get('next') or \
        flask.request.referrer or \
        '/'
    if url == flask.request.url:
        return '/'
    return url


@app.template_global()
def modify_query(**new_values):
    args = flask.request.args.copy()

    for key, value in new_values.items():
        args[key] = value

    return '{}?{}'.format(flask.request.path, url_encode(args))


@app.template_global()
def filter_truthy(input_list):
    ''' Jinja2 can't into list comprehension so this is for
        the search_results.html template '''
    return [item for item in input_list if item]


@app.errorhandler(404)
def not_found(error):
    return flask.render_template('404.html'), 404


@app.before_request
def before_request():
    flask.g.user = None
    if 'user_id' in flask.session:
        user = models.User.by_id(flask.session['user_id'])
        if not user:
            return logout()

        flask.g.user = user

        if 'timeout' not in flask.session or flask.session['timeout'] < datetime.now():
            flask.session['timeout'] = datetime.now() + timedelta(days=7)
            flask.session.permanent = True
            flask.session.modified = True

        if flask.g.user.status == models.UserStatusType.BANNED:
            return 'You are banned.', 403


def _generate_query_string(term, category, filter, user):
    params = {}
    if term:
        params['q'] = str(term)
    if category:
        params['c'] = str(category)
    if filter:
        params['f'] = str(filter)
    if user:
        params['u'] = str(user)
    return params


@app.template_filter('utc_time')
def get_utc_timestamp(datetime_str):
    ''' Returns a UTC POSIX timestamp, as seconds '''
    UTC_EPOCH = datetime.utcfromtimestamp(0)
    return int((datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S') - UTC_EPOCH).total_seconds())


@app.template_filter('display_time')
def get_display_time(datetime_str):
    return datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M')


@app.route('/rss', defaults={'rss': True})
@app.route('/', defaults={'rss': False})
def home(rss):
    if flask.request.args.get('page') == 'rss':
        rss = True

    term = flask.request.args.get('q', flask.request.args.get('term'))
    sort = flask.request.args.get('s')
    order = flask.request.args.get('o')
    category = flask.request.args.get('c', flask.request.args.get('cats'))
    quality_filter = flask.request.args.get('f', flask.request.args.get('filter'))
    user_name = flask.request.args.get('u', flask.request.args.get('user'))
    page = flask.request.args.get('p', flask.request.args.get('offset', 1, int), int)

    per_page = app.config.get('RESULTS_PER_PAGE')
    if not per_page:
        per_page = DEFAULT_PER_PAGE

    user_id = None
    if user_name:
        user = models.User.by_username(user_name)
        if not user:
            flask.abort(404)
        user_id = user.id

    query_args = {
        'user': user_id,
        'sort': sort or 'id',
        'order': order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page,
        'rss': rss,
        'per_page': per_page
    }

    if flask.g.user:
        query_args['logged_in_user'] = flask.g.user
        if flask.g.user.is_admin:  # God mode
            query_args['admin'] = True

    # If searching, we get results from elastic search
    use_elastic = app.config.get('USE_ELASTIC_SEARCH')
    if use_elastic and term:
        query_args['term'] = term

        max_search_results = app.config.get('ES_MAX_SEARCH_RESULT')
        if not max_search_results:
            max_search_results = DEFAULT_MAX_SEARCH_RESULT

        # Only allow up to (max_search_results / page) pages
        max_page = min(query_args['page'], int(math.ceil(max_search_results / float(per_page))))

        query_args['page'] = max_page
        query_args['max_search_results'] = max_search_results

        query_results = search_elastic(**query_args)

        if rss:
            return render_rss('/', query_results, use_elastic=True)
        else:
            rss_query_string = _generate_query_string(term, category, quality_filter, user_name)
            max_results = min(max_search_results, query_results['hits']['total'])
            # change p= argument to whatever you change page_parameter to or pagination breaks
            pagination = Pagination(p=query_args['page'], per_page=per_page,
                                    total=max_results, bs_version=3, page_parameter='p',
                                    display_msg=SERACH_PAGINATE_DISPLAY_MSG)
            return flask.render_template('home.html',
                                         use_elastic=True,
                                         pagination=pagination,
                                         torrent_query=query_results,
                                         search=query_args,
                                         rss_filter=rss_query_string)
    else:
        # If ES is enabled, default to db search for browsing
        if use_elastic:
            query_args['term'] = ''
        else:  # Otherwise, use db search for everything
            query_args['term'] = term or ''

        query = search_db(**query_args)
        if rss:
            return render_rss('/', query, use_elastic=False)
        else:
            rss_query_string = _generate_query_string(term, category, quality_filter, user_name)
            # Use elastic is always false here because we only hit this section
            # if we're browsing without a search term (which means we default to DB)
            # or if ES is disabled
            return flask.render_template('home.html',
                                         use_elastic=False,
                                         torrent_query=query,
                                         search=query_args,
                                         rss_filter=rss_query_string)


@app.route('/user/<user_name>', methods=['GET', 'POST'])
def view_user(user_name):
    user = models.User.by_username(user_name)

    if not user:
        flask.abort(404)

    if flask.g.user and flask.g.user.id != user.id:
        admin = flask.g.user.is_admin
        superadmin = flask.g.user.is_superadmin
    else:
        admin = False
        superadmin = False

    form = forms.UserForm()
    form.user_class.choices = _create_user_class_choices()
    if flask.request.method == 'POST' and form.validate():
        selection = form.user_class.data

        if selection == 'regular':
            user.level = models.UserLevelType.REGULAR
        elif selection == 'trusted':
            user.level = models.UserLevelType.TRUSTED
        db.session.add(user)
        db.session.commit()

        return flask.redirect('/user/' + user.username)

    level = 'Regular'
    if user.is_admin:
        level = 'Moderator'
    if user.is_superadmin:  # check this second because user can be admin AND superadmin
        level = 'Administrator'
    elif user.is_trusted:
        level = 'Trusted'

    term = flask.request.args.get('q')
    sort = flask.request.args.get('s')
    order = flask.request.args.get('o')
    category = flask.request.args.get('c')
    quality_filter = flask.request.args.get('f')
    page = flask.request.args.get('p')
    if page:
        page = int(page)

    per_page = app.config.get('RESULTS_PER_PAGE')
    if not per_page:
        per_page = DEFAULT_PER_PAGE

    query_args = {
        'term': term or '',
        'user': user.id,
        'sort': sort or 'id',
        'order': order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page or 1,
        'rss': False,
        'per_page': per_page
    }

    if flask.g.user:
        query_args['logged_in_user'] = flask.g.user
        if flask.g.user.is_admin:  # God mode
            query_args['admin'] = True

    # Use elastic search for term searching
    rss_query_string = _generate_query_string(term, category, quality_filter, user_name)
    use_elastic = app.config.get('USE_ELASTIC_SEARCH')
    if use_elastic and term:
        query_args['term'] = term

        max_search_results = app.config.get('ES_MAX_SEARCH_RESULT')
        if not max_search_results:
            max_search_results = DEFAULT_MAX_SEARCH_RESULT

        # Only allow up to (max_search_results / page) pages
        max_page = min(query_args['page'], int(math.ceil(max_search_results / float(per_page))))

        query_args['page'] = max_page
        query_args['max_search_results'] = max_search_results

        query_results = search_elastic(**query_args)

        max_results = min(max_search_results, query_results['hits']['total'])
        # change p= argument to whatever you change page_parameter to or pagination breaks
        pagination = Pagination(p=query_args['page'], per_page=per_page,
                                total=max_results, bs_version=3, page_parameter='p',
                                display_msg=SERACH_PAGINATE_DISPLAY_MSG)
        return flask.render_template('user.html',
                                     use_elastic=True,
                                     pagination=pagination,
                                     torrent_query=query_results,
                                     search=query_args,
                                     user=user,
                                     user_page=True,
                                     rss_filter=rss_query_string,
                                     level=level,
                                     admin=admin,
                                     superadmin=superadmin,
                                     form=form)
    # Similar logic as home page
    else:
        if use_elastic:
            query_args['term'] = ''
        else:
            query_args['term'] = term or ''
        query = search_db(**query_args)
        return flask.render_template('user.html',
                                     use_elastic=False,
                                     torrent_query=query,
                                     search=query_args,
                                     user=user,
                                     user_page=True,
                                     rss_filter=rss_query_string,
                                     level=level,
                                     admin=admin,
                                     superadmin=superadmin,
                                     form=form)


@app.template_filter('rfc822')
def _jinja2_filter_rfc822(date, fmt=None):
    return formatdate(float(date.strftime('%s')))


@app.template_filter('rfc822_es')
def _jinja2_filter_rfc822(datestr, fmt=None):
    return formatdate(float(datetime.strptime(datestr, '%Y-%m-%dT%H:%M:%S').strftime('%s')))


def render_rss(label, query, use_elastic):
    rss_xml = flask.render_template('rss.xml',
                                    use_elastic=use_elastic,
                                    term=label,
                                    site_url=flask.request.url_root,
                                    torrent_query=query)
    response = flask.make_response(rss_xml)
    response.headers['Content-Type'] = 'application/xml'
    # Cache for an hour
    response.headers['Cache-Control'] = 'max-age={}'.format(1 * 5 * 60)
    return response


# @app.route('/about', methods=['GET'])
# def about():
    # return flask.render_template('about.html')


@app.route('/login', methods=['GET', 'POST'])
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

        if (not user or password != user.password_hash
                or user.status == models.UserStatusType.INACTIVE):
            flask.flash(flask.Markup(
                '<strong>Login failed!</strong> Incorrect username or password.'), 'danger')
            return flask.redirect(flask.url_for('login'))

        user.last_login_date = datetime.utcnow()
        user.last_login_ip = ipaddress.ip_address(flask.request.remote_addr).packed
        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        flask.session['user_id'] = user.id
        flask.session.permanent = True
        flask.session.modified = True

        return flask.redirect(redirect_url())

    return flask.render_template('login.html', form=form)


@app.route('/logout')
def logout():
    flask.g.user = None
    flask.session.permanent = False
    flask.session.modified = False

    response = flask.make_response(flask.redirect(redirect_url()))
    response.set_cookie(app.session_cookie_name, expires=0)
    return response


@app.route('/register', methods=['GET', 'POST'])
def register():
    if flask.g.user:
        return flask.redirect(redirect_url())

    form = forms.RegisterForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
        user = models.User(username=form.username.data.strip(),
                           email=form.email.data.strip(), password=form.password.data)
        user.last_login_ip = ipaddress.ip_address(flask.request.remote_addr).packed
        db.session.add(user)
        db.session.commit()

        if config.USE_EMAIL_VERIFICATION:  # force verification, enable email
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


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not flask.g.user:
        return flask.redirect('/')  # so we dont get stuck in infinite loop when signing out

    form = forms.ProfileForm(flask.request.form)

    level = 'Regular'
    if flask.g.user.is_admin:
        level = 'Moderator'
    if flask.g.user.is_superadmin:  # check this second because we can be admin AND superadmin
        level = 'Administrator'
    elif flask.g.user.is_trusted:
        level = 'Trusted'

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
                '<strong>Email successfully changed!</strong>'), 'info')
        if new_password:
            if form.current_password.data != user.password_hash:
                flask.flash(flask.Markup(
                    '<strong>Password change failed!</strong> Incorrect password.'), 'danger')
                return flask.redirect('/profile')
            user.password_hash = form.new_password.data
            flask.flash(flask.Markup(
                '<strong>Password successfully changed!</strong>'), 'info')

        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        return flask.redirect('/profile')

    current_email = models.User.by_id(flask.g.user.id).email

    return flask.render_template('profile.html', form=form, email=current_email, level=level)


@app.route('/user/activate/<payload>')
def activate_user(payload):
    s = get_serializer()
    try:
        user_id = s.loads(payload)
    except BadSignature:
        flask.abort(404)

    user = models.User.by_id(user_id)

    if not user:
        flask.abort(404)

    user.status = models.UserStatusType.ACTIVE

    db.session.add(user)
    db.session.commit()

    return flask.redirect('/login')


@utils.cached_function
def _create_upload_category_choices():
    ''' Turns categories in the database into a list of (id, name)s '''
    choices = [('', '[Select a category]')]
    for main_cat in models.MainCategory.query.order_by(models.MainCategory.id):
        choices.append((main_cat.id_as_string, main_cat.name, True))
        for sub_cat in main_cat.sub_categories:
            choices.append((sub_cat.id_as_string, ' - ' + sub_cat.name))
    return choices


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    form = forms.UploadForm(CombinedMultiDict((flask.request.files, flask.request.form)))
    #print('{0} - {1}'.format(flask.request.files, flask.request.form))
    form.category.choices = _create_upload_category_choices()
    if flask.request.method == 'POST' and form.validate():
        torrent = backend.handle_torrent_upload(form, flask.g.user)

        return flask.redirect('/view/' + str(torrent.id))
    else:
        # If we get here with a POST, it means the form data was invalid: return a non-okay status
        status_code = 400 if flask.request.method == 'POST' else 200
        return flask.render_template('upload.html', form=form, user=flask.g.user), status_code


@app.route('/view/<int:torrent_id>')
def view_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent:
        flask.abort(404)

    if torrent.deleted and (not flask.g.user or not flask.g.user.is_admin):
        flask.abort(404)

    if flask.g.user:
        can_edit = flask.g.user is torrent.user or flask.g.user.is_admin
    else:
        can_edit = False

    files = None
    if torrent.filelist:
        files = json.loads(torrent.filelist.filelist_blob.decode('utf-8'))

    return flask.render_template('view.html', torrent=torrent,
                                 files=files,
                                 can_edit=can_edit)


@app.route('/view/<int:torrent_id>/edit', methods=['GET', 'POST'])
def edit_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)
    form = forms.EditForm(flask.request.form)
    form.category.choices = _create_upload_category_choices()
    category = str(torrent.main_category_id) + "_" + str(torrent.sub_category_id)

    if not torrent:
        flask.abort(404)

    if torrent.deleted and (not flask.g.user or not flask.g.user.is_admin):
        flask.abort(404)

    if not flask.g.user or (flask.g.user is not torrent.user and not flask.g.user.is_admin):
        flask.abort(403)

    if flask.request.method == 'POST' and form.validate():
        # Form has been sent, edit torrent with data.
        torrent.main_category_id, torrent.sub_category_id = \
            form.category.parsed_data.get_category_ids()
        torrent.display_name = (form.display_name.data or '').strip()
        torrent.information = (form.information.data or '').strip()
        torrent.description = (form.description.data or '').strip()
        if flask.g.user.is_admin:
            torrent.deleted = form.is_deleted.data
        torrent.hidden = form.is_hidden.data
        torrent.remake = form.is_remake.data
        torrent.complete = form.is_complete.data
        torrent.anonymous = form.is_anonymous.data

        db.session.commit()

        flask.flash(flask.Markup(
            'Torrent has been successfully edited! Changes might take a few minutes to show up.'), 'info')

        return flask.redirect('/view/' + str(torrent_id))
    else:
        # Setup form with pre-formatted form.
        form.category.data = category
        form.display_name.data = torrent.display_name
        form.information.data = torrent.information
        form.description.data = torrent.description
        form.is_hidden.data = torrent.hidden
        if flask.g.user.is_admin:
            form.is_deleted.data = torrent.deleted
        form.is_remake.data = torrent.remake
        form.is_complete.data = torrent.complete
        form.is_anonymous.data = torrent.anonymous

        return flask.render_template('edit.html',
                                     form=form,
                                     torrent=torrent,
                                     admin=flask.g.user.is_admin)


@app.route('/view/<int:torrent_id>/magnet')
def redirect_magnet(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent:
        flask.abort(404)

    return flask.redirect(torrents.create_magnet(torrent))


@app.route('/view/<int:torrent_id>/torrent')
def download_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent:
        flask.abort(404)

    resp = flask.Response(_get_cached_torrent_file(torrent))
    resp.headers['Content-Type'] = 'application/x-bittorrent'
    resp.headers['Content-Disposition'] = 'inline; filename*=UTF-8\'\'{}'.format(
        quote(torrent.torrent_name.encode('utf-8')))

    return resp


def _get_cached_torrent_file(torrent):
    # Note: obviously temporary
    cached_torrent = os.path.join(app.config['BASE_DIR'],
                                  'torrent_cache', str(torrent.id) + '.torrent')
    if not os.path.exists(cached_torrent):
        with open(cached_torrent, 'wb') as out_file:
            out_file.write(torrents.create_bencoded_torrent(torrent))

    return open(cached_torrent, 'rb')


def get_serializer(secret_key=None):
    if secret_key is None:
        secret_key = app.secret_key
    return URLSafeSerializer(secret_key)


def get_activation_link(user):
    s = get_serializer()
    payload = s.dumps(user.id)
    return flask.url_for('activate_user', payload=payload, _external=True)


def send_verification_email(to_address, activ_link):
    ''' this is until we have our own mail server, obviously.
     This can be greatly cut down if on same machine.
     probably can get rid of all but msg formatting/building,
     init line and sendmail line if local SMTP server '''

    msg_body = 'Please click on: ' + activ_link + ' to activate your account.\n\n\nUnsubscribe:'

    msg = MIMEMultipart()
    msg['Subject'] = 'Verification Link'
    msg['From'] = config.MAIL_FROM_ADDRESS
    msg['To'] = to_address
    msg.attach(MIMEText(msg_body, 'plain'))

    server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
    server.set_debuglevel(1)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
    server.sendmail(config.SMTP_USERNAME, to_address, msg.as_string())
    server.quit()


def _create_user_class_choices():
    choices = [('regular', 'Regular')]
    if flask.g.user and flask.g.user.is_superadmin:
        choices.append(('trusted', 'Trusted'))
    return choices


# #################################### STATIC PAGES ####################################
@app.route('/rules', methods=['GET'])
def site_rules():
    return flask.render_template('rules.html')


@app.route('/help', methods=['GET'])
def site_help():
    return flask.render_template('help.html')


# #################################### API ROUTES ####################################
@app.route('/api/upload', methods=['POST'])
def api_upload():
    is_valid_user, user, debug = api_handler.validate_user(flask.request)
    if not is_valid_user:
        return flask.make_response(flask.jsonify({"Failure": "Invalid username or password."}), 400)
    api_response = api_handler.api_upload(flask.request, user)
    return api_response

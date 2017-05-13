import flask
from werkzeug.datastructures import CombinedMultiDict
from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, utils
from nyaa import torrents
from nyaa import backend
from nyaa import api_handler
import config

import json
import re
from datetime import datetime
import ipaddress
import os.path
import base64
from urllib.parse import quote
import sqlalchemy_fulltext.modes as FullTextMode
from sqlalchemy_fulltext import FullTextSearch
import shlex
from werkzeug import url_encode

from itsdangerous import URLSafeSerializer, BadSignature

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

DEBUG_API = False


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


def search(term='', user=None, sort='id', order='desc', category='0_0', quality_filter='0', page=1, rss=False, admin=False):
    sort_keys = {
        'id': models.Torrent.id,
        'size': models.Torrent.filesize,
        'name': models.Torrent.display_name,
        'seeders': models.Statistic.seed_count,
        'leechers': models.Statistic.leech_count,
        'downloads': models.Statistic.download_count
    }

    sort_ = sort.lower()
    if sort_ not in sort_keys:
        flask.abort(400)
    sort = sort_keys[sort]

    order_keys = {
        'desc': 'desc',
        'asc': 'asc'
    }

    order_ = order.lower()
    if order_ not in order_keys:
        flask.abort(400)

    filter_keys = {
        '0': None,
        '1': (models.TorrentFlags.REMAKE, False),
        '2': (models.TorrentFlags.TRUSTED, True),
        '3': (models.TorrentFlags.COMPLETE, True)
    }

    sentinel = object()
    filter_tuple = filter_keys.get(quality_filter.lower(), sentinel)
    if filter_tuple is sentinel:
        flask.abort(400)

    if user:
        user = models.User.by_id(user)
        if not user:
            flask.abort(404)
        user = user.id

    main_category = None
    sub_category = None
    main_cat_id = 0
    sub_cat_id = 0
    if category:
        cat_match = re.match(r'^(\d+)_(\d+)$', category)
        if not cat_match:
            flask.abort(400)

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        if main_cat_id > 0:
            if sub_cat_id > 0:
                sub_category = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)
            else:
                main_category = models.MainCategory.by_id(main_cat_id)

            if not category:
                flask.abort(400)

    # Force sort by id desc if rss
    if rss:
        sort = sort_keys['id']
        order = 'desc'
        page = 1

    same_user = False
    if flask.g.user:
        same_user = flask.g.user.id == user

    if term:
        query = db.session.query(models.TorrentNameSearch)
    else:
        query = models.Torrent.query

    # Filter by user
    if user:
        query = query.filter(models.Torrent.uploader_id == user)
        # If admin, show everything
        if not admin:
            # If user is not logged in or the accessed feed doesn't belong to user,
            # hide anonymous torrents belonging to the queried user
            if not same_user:
                query = query.filter(models.Torrent.flags.op('&')(
                    int(models.TorrentFlags.ANONYMOUS | models.TorrentFlags.DELETED)).is_(False))

    if main_category:
        query = query.filter(models.Torrent.main_category_id == main_cat_id)
    elif sub_category:
        query = query.filter((models.Torrent.main_category_id == main_cat_id) &
                             (models.Torrent.sub_category_id == sub_cat_id))

    if filter_tuple:
        query = query.filter(models.Torrent.flags.op('&')(int(filter_tuple[0])).is_(filter_tuple[1]))

    # If admin, show everything
    if not admin:
        query = query.filter(models.Torrent.flags.op('&')(
            int(models.TorrentFlags.HIDDEN | models.TorrentFlags.DELETED)).is_(False))

    if term:
        for item in shlex.split(term, posix=False):
            if len(item) >= 2:
                query = query.filter(FullTextSearch(
                    item, models.TorrentNameSearch, FullTextMode.NATURAL))

    # Sort and order
    if sort.class_ != models.Torrent:
        query = query.join(sort.class_)

    query = query.order_by(getattr(sort, order)())

    if rss:
        query = query.limit(app.config['RESULTS_PER_PAGE'])
    else:
        query = query.paginate_faste(page, per_page=app.config['RESULTS_PER_PAGE'], step=5)

    return query


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


@app.route('/rss', defaults={'rss': True})
@app.route('/', defaults={'rss': False})
def home(rss):
    if flask.request.args.get('page') == 'rss':
        rss = True

    term = flask.request.args.get('q')
    sort = flask.request.args.get('s')
    order = flask.request.args.get('o')
    category = flask.request.args.get('c')
    quality_filter = flask.request.args.get('f')
    user_name = flask.request.args.get('u')
    page = flask.request.args.get('p')
    if page:
        page = int(page)

    user_id = None
    if user_name:
        user = models.User.by_username(user_name)
        if not user:
            flask.abort(404)
        user_id = user.id

    query_args = {
        'term': term or '',
        'user': user_id,
        'sort': sort or 'id',
        'order': order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page or 1,
        'rss': rss
    }

    # God mode
    if flask.g.user and flask.g.user.is_admin:
        query_args['admin'] = True

    query = search(**query_args)
    
    if rss:
        return render_rss('/', query)
    else:
        rss_query_string = _generate_query_string(term, category, quality_filter, user_name)
        return flask.render_template('home.html',
                                     torrent_query=query,
                                     search=query_args,
                                     rss_filter=rss_query_string)


@app.route('/user/<user_name>')
def view_user(user_name):
    user = models.User.by_username(user_name)

    if not user:
        flask.abort(404)

    term = flask.request.args.get('q')
    sort = flask.request.args.get('s')
    order = flask.request.args.get('o')
    category = flask.request.args.get('c')
    quality_filter = flask.request.args.get('f')
    page = flask.request.args.get('p')
    if page:
        page = int(page)

    query_args = {
        'term': term or '',
        'user': user.id,
        'sort': sort or 'id',
        'order': order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page or 1,
        'rss': False
    }

    # God mode
    if flask.g.user and flask.g.user.is_admin:
        query_args['admin'] = True

    query = search(**query_args)

    rss_query_string = _generate_query_string(term, category, quality_filter, user_name)
    return flask.render_template('user.html',
                                 torrent_query=query,
                                 search=query_args,
                                 user=user,
                                 user_page=True,
                                 rss_filter=rss_query_string)


@app.template_filter('rfc822')
def _jinja2_filter_rfc822(date, fmt=None):
    return formatdate(float(date.strftime('%s')))


def render_rss(label, query):
    rss_xml = flask.render_template('rss.xml',
                                    term=label,
                                    site_url=flask.request.url_root,
                                    query=query)
    response = flask.make_response(rss_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


#@app.route('/about', methods=['GET'])
# def about():
#    return flask.render_template('about.html')


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

        if not user or password != user.password_hash or user.status == models.UserStatusType.INACTIVE:
            flask.flash(flask.Markup(
                '<strong>Login failed!</strong> Incorrect username or password.'), 'danger')
            return flask.redirect(flask.url_for('login'))

        user.last_login_date = datetime.utcnow()
        user.last_login_ip = ipaddress.ip_address(flask.request.remote_addr).packed
        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        flask.session['user_id'] = user.id

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
            return flask.redirect(redirect_url())

    return flask.render_template('register.html', form=form)


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not flask.g.user:
        return flask.redirect('/')  # so we dont get stuck in infinite loop when signing out

    form = forms.ProfileForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
        user = flask.g.user
        new_email = form.email.data
        new_password = form.new_password.data

        if new_email:
            user.email = form.email.data

        if new_password:
            if form.current_password.data != user.password_hash:
                flask.flash(flask.Markup(
                    '<strong>Password change failed!</strong> Incorrect password.'), 'danger')
                return flask.redirect('/profile')
            user.password_hash = form.new_password.data

        db.session.add(user)
        db.session.commit()

        flask.g.user = user
        flask.session['user_id'] = user.id

    return flask.render_template('profile.html', form=form)


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
    form = forms.CommentForm()

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
        files = utils.flattenDict(json.loads(torrent.filelist.filelist_blob.decode('utf-8')))

    comments = models.Comment.query.filter_by(torrent=torrent_id)
    comment_count = comments.count()

    return flask.render_template('view.html', torrent=torrent,
                                 files=files,
                                 form=form,
                                 comments=comments,
                                 comment_count=comment_count,
                                 can_edit=can_edit)


@app.route('/view/<int:torrent_id>/submit_comment', methods=['POST'])
def submit_comment(torrent_id):
    form = forms.CommentForm(flask.request.form)

    if flask.request.method == 'POST' and form.validate():
        comment_text = (form.comment.data or '').strip()

        # Null entry for User just means Anonymous
        current_user_id = flask.g.user.id if flask.g.user else None
        comment = models.Comment(
            torrent=torrent_id,
            user_id=current_user_id,
            text=comment_text)

        db.session.add(comment)
        db.session.commit()

    return flask.redirect(flask.url_for('view_torrent', torrent_id=torrent_id))

@app.route('/view/<int:torrent_id>/delete_comment/<int:comment_id>')
def delete_comment(torrent_id, comment_id):
    if flask.g.user is not None and flask.g.user.is_admin:
        models.Comment.query.filter_by(id=comment_id).delete()
        db.session.commit()
    else:
        flask.abort(403)
    
    return flask.redirect(flask.url_for('view_torrent', torrent_id=torrent_id))     


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
        torrent.main_category_id, torrent.sub_category_id = form.category.parsed_data.get_category_ids()
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

        return flask.render_template('edit.html', form=form, torrent=torrent, admin=flask.g.user.is_admin)


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
    ''' this is until we have our own mail server, obviously. This can be greatly cut down if on same machine.
     probably can get rid of all but msg formatting/building, init line and sendmail line if local SMTP server '''

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


#################################### STATIC PAGES ####################################
@app.route('/rules', methods=['GET'])
def site_rules():
    return flask.render_template('rules.html')


@app.route('/help', methods=['GET'])
def site_help():
    return flask.render_template('help.html')


#################################### API ROUTES ####################################
# DISABLED FOR NOW
@app.route('/api/upload', methods=['POST'])
def api_upload():
    api_response = api_handler.api_upload(flask.request)
    return api_response

import binascii
import math
import time
from ipaddress import ip_address
from itertools import chain

import flask
from flask_paginate import Pagination

from itsdangerous import BadSignature, URLSafeSerializer

from nyaa import forms, models
from nyaa.extensions import db
from nyaa.search import (DEFAULT_MAX_SEARCH_RESULT, DEFAULT_PER_PAGE, SERACH_PAGINATE_DISPLAY_MSG,
                         _generate_query_string, search_db, search_db_baked, search_elastic)
from nyaa.utils import admin_only, chain_get, sha1_hash

app = flask.current_app
bp = flask.Blueprint('users', __name__)


@bp.route('/user/<user_name>', methods=['GET', 'POST'])
def view_user(user_name):
    user = models.User.by_username(user_name)

    if not user:
        flask.abort(404)

    admin_form = None
    ban_form = None
    bans = None
    ipbanned = None
    nuke_form = None
    if flask.g.user and flask.g.user.is_moderator and flask.g.user.level > user.level:
        admin_form = forms.UserForm()
        default, admin_form.user_class.choices = _create_user_class_choices(user)
        if flask.request.method == 'GET':
            admin_form.user_class.data = default

        ban_form = forms.BanForm()
        nuke_form = forms.NukeForm()
        if flask.request.method == 'POST':
            doban = (ban_form.ban_user.data or ban_form.unban.data or ban_form.ban_userip.data)
        bans = models.Ban.banned(user.id, user.last_login_ip).all()
        ipbanned = list(filter(lambda b: b.user_ip == user.last_login_ip, bans))

    url = flask.url_for('users.view_user', user_name=user.username)
    if flask.request.method == 'POST' and admin_form and not doban and admin_form.validate():
        selection = admin_form.user_class.data
        mapping = {'regular': models.UserLevelType.REGULAR,
                   'trusted': models.UserLevelType.TRUSTED,
                   'moderator': models.UserLevelType.MODERATOR}

        if mapping[selection] != user.level:
            user.level = mapping[selection]
            log = "[{}]({}) changed to {} user".format(user_name, url, selection)
            adminlog = models.AdminLog(log=log, admin_id=flask.g.user.id)
            db.session.add(adminlog)

        if admin_form.activate_user.data and not user.is_banned:
            if user.status != models.UserStatusType.ACTIVE:
                user.status = models.UserStatusType.ACTIVE
                adminlog = models.AdminLog("[{}]({}) was manually activated"
                                           .format(user_name, url), admin_id=flask.g.user.id)
                db.session.add(adminlog)
                flask.flash('{} was manually activated'.format(user_name), 'success')

        db.session.add(user)
        db.session.commit()

        return flask.redirect(url)

    if flask.request.method == 'POST' and ban_form and doban and ban_form.validate():
        if (ban_form.ban_user.data and user.is_banned) or \
                (ban_form.ban_userip.data and ipbanned) or \
                (ban_form.unban.data and not user.is_banned and not bans):
            flask.flash(flask.Markup('What the fuck are you doing?'), 'danger')
            return flask.redirect(url)

        user_str = "[{0}]({1})".format(user.username, url)

        if ban_form.unban.data:
            action = "unbanned"
            user.status = models.UserStatusType.ACTIVE
            db.session.add(user)

            for ban in bans:
                if ban.user_ip:
                    user_str += " IP({0})".format(ip_address(ban.user_ip))
                db.session.delete(ban)
        else:
            action = "banned"
            user.status = models.UserStatusType.BANNED
            db.session.add(user)

            ban = models.Ban(admin_id=flask.g.user.id, user_id=user.id, reason=ban_form.reason.data)
            db.session.add(ban)

            if ban_form.ban_userip.data:
                ban.user_ip = ip_address(user.last_login_ip)
                user_str += " IP({0})".format(ban.user_ip)
                ban.user_ip = ban.user_ip.packed

        log = "User {0} has been {1}.".format(user_str, action)
        adminlog = models.AdminLog(log=log, admin_id=flask.g.user.id)
        db.session.add(adminlog)

        db.session.commit()

        flask.flash(flask.Markup('User has been successfully {0}.'.format(action)), 'success')
        return flask.redirect(url)

    req_args = flask.request.args

    search_term = chain_get(req_args, 'q', 'term')

    sort_key = req_args.get('s')
    sort_order = req_args.get('o')

    category = chain_get(req_args, 'c', 'cats')
    quality_filter = chain_get(req_args, 'f', 'filter')

    page_number = chain_get(req_args, 'p', 'page', 'offset')
    try:
        page_number = max(1, int(page_number))
    except (ValueError, TypeError):
        page_number = 1

    results_per_page = app.config.get('RESULTS_PER_PAGE', DEFAULT_PER_PAGE)

    query_args = {
        'term': search_term or '',
        'user': user.id,
        'sort': sort_key or 'id',
        'order': sort_order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page_number,
        'rss': False,
        'per_page': results_per_page
    }

    if flask.g.user:
        query_args['logged_in_user'] = flask.g.user
        if flask.g.user.is_moderator:  # God mode
            query_args['admin'] = True

    # Use elastic search for term searching
    rss_query_string = _generate_query_string(search_term, category, quality_filter, user_name)
    use_elastic = app.config.get('USE_ELASTIC_SEARCH')
    if use_elastic and search_term:
        query_args['term'] = search_term

        max_search_results = app.config.get('ES_MAX_SEARCH_RESULT', DEFAULT_MAX_SEARCH_RESULT)

        # Only allow up to (max_search_results / page) pages
        max_page = min(query_args['page'], int(math.ceil(max_search_results / results_per_page)))

        query_args['page'] = max_page
        query_args['max_search_results'] = max_search_results

        query_results = search_elastic(**query_args)

        max_results = min(max_search_results, query_results['hits']['total'])
        # change p= argument to whatever you change page_parameter to or pagination breaks
        pagination = Pagination(p=query_args['page'], per_page=results_per_page,
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
                                     admin_form=admin_form,
                                     ban_form=ban_form,
                                     nuke_form=nuke_form,
                                     bans=bans,
                                     ipbanned=ipbanned)
    # Similar logic as home page
    else:
        if use_elastic:
            query_args['term'] = ''
        else:
            query_args['term'] = search_term or ''
        if app.config['USE_BAKED_SEARCH']:
            query = search_db_baked(**query_args)
        else:
            query = search_db(**query_args)
        return flask.render_template('user.html',
                                     use_elastic=False,
                                     torrent_query=query,
                                     search=query_args,
                                     user=user,
                                     user_page=True,
                                     rss_filter=rss_query_string,
                                     admin_form=admin_form,
                                     ban_form=ban_form,
                                     nuke_form=nuke_form,
                                     bans=bans,
                                     ipbanned=ipbanned)


@bp.route('/user/<user_name>/comments')
def view_user_comments(user_name):
    user = models.User.by_username(user_name)

    if not user:
        flask.abort(404)

    # Only moderators get to see all comments for now
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)

    page_number = flask.request.args.get('p')
    try:
        page_number = max(1, int(page_number))
    except (ValueError, TypeError):
        page_number = 1

    comments_per_page = 100

    comments_query = (models.Comment.query.filter(models.Comment.user == user)
                                          .order_by(models.Comment.created_time.desc()))
    comments_query = comments_query.paginate_faste(page_number, per_page=comments_per_page, step=5)
    return flask.render_template('user_comments.html',
                                 comments_query=comments_query,
                                 user=user)


@bp.route('/user/activate/<payload>')
def activate_user(payload):
    if app.config['MAINTENANCE_MODE']:
        flask.flash(flask.Markup('<strong>Activations are currently disabled.</strong>'), 'danger')
        return flask.redirect(flask.url_for('main.home'))

    s = get_serializer()
    try:
        user_id = s.loads(payload)
    except BadSignature:
        flask.abort(404)

    user = models.User.by_id(user_id)

    # Only allow activating inactive users
    if not user or user.status != models.UserStatusType.INACTIVE:
        flask.abort(404)

    # Set user active
    user.status = models.UserStatusType.ACTIVE
    db.session.add(user)
    db.session.commit()

    # Log user in
    flask.g.user = user
    flask.session['user_id'] = user.id
    flask.session.permanent = True
    flask.session.modified = True

    flask.flash(flask.Markup("You've successfully verified your account!"), 'success')
    return flask.redirect(flask.url_for('main.home'))


@bp.route('/user/<user_name>/nuke/torrents', methods=['POST'])
@admin_only
def nuke_user_torrents(user_name):
    user = models.User.by_username(user_name)
    if not user:
        flask.abort(404)

    nuke_form = forms.NukeForm(flask.request.form)
    if not nuke_form.validate():
        flask.abort(401)
    url = flask.url_for('users.view_user', user_name=user.username)
    nyaa_banned = 0
    sukebei_banned = 0
    for t in chain(user.nyaa_torrents, user.sukebei_torrents):
        t.deleted = True
        t.banned = True
        t.stats.seed_count = 0
        t.stats.leech_count = 0
        db.session.add(t)
        if isinstance(t, models.NyaaTorrent):
            db.session.add(models.NyaaTrackerApi(t.info_hash, 'remove'))
            nyaa_banned += 1
        else:
            db.session.add(models.SukebeiTrackerApi(t.info_hash, 'remove'))
            sukebei_banned += 1

    for log_flavour, num in ((models.NyaaAdminLog, nyaa_banned),
                             (models.SukebeiAdminLog, sukebei_banned)):
        if num > 0:
            log = "Nuked {0} torrents of [{1}]({2})".format(num,
                                                            user.username,
                                                            url)
            adminlog = log_flavour(log=log, admin_id=flask.g.user.id)
            db.session.add(adminlog)

    db.session.commit()
    flask.flash('Torrents of {0} have been nuked.'.format(user.username),
                'success')
    return flask.redirect(url)


@bp.route('/user/<user_name>/nuke/comments', methods=['POST'])
@admin_only
def nuke_user_comments(user_name):
    user = models.User.by_username(user_name)
    if not user:
        flask.abort(404)

    nuke_form = forms.NukeForm(flask.request.form)
    if not nuke_form.validate():
        flask.abort(401)
    url = flask.url_for('users.view_user', user_name=user.username)
    nyaa_deleted = 0
    sukebei_deleted = 0
    nyaa_torrents = set()
    sukebei_torrents = set()
    for c in chain(user.nyaa_comments, user.sukebei_comments):
        nyaa_torrents.add(c.torrent_id)
        sukebei_torrents.add(c.torrent_id)
        db.session.delete(c)
        if isinstance(c, models.NyaaComment):
            nyaa_deleted += 1
        else:
            sukebei_deleted += 1

    for tid in nyaa_torrents:
        models.NyaaTorrent.update_comment_count_db(tid)
    for tid in sukebei_torrents:
        models.SukebeiTorrent.update_comment_count_db(tid)

    for log_flavour, num in ((models.NyaaAdminLog, nyaa_deleted),
                             (models.SukebeiAdminLog, sukebei_deleted)):
        if num > 0:
            log = "Nuked {0} comments of [{1}]({2})".format(num,
                                                            user.username,
                                                            url)
            adminlog = log_flavour(log=log, admin_id=flask.g.user.id)
            db.session.add(adminlog)

    db.session.commit()
    flask.flash('Comments of {0} have been nuked.'.format(user.username),
                'success')
    return flask.redirect(url)


def _create_user_class_choices(user):
    choices = [('regular', 'Regular')]
    default = 'regular'
    if flask.g.user:
        if flask.g.user.is_moderator:
            choices.append(('trusted', 'Trusted'))
        if flask.g.user.is_superadmin:
            choices.append(('moderator', 'Moderator'))

        if user:
            if user.is_moderator:
                default = 'moderator'
            elif user.is_trusted:
                default = 'trusted'
            elif user.is_banned:
                default = 'banned'

    return default, choices


def get_serializer(secret_key=None):
    if secret_key is None:
        secret_key = app.secret_key
    return URLSafeSerializer(secret_key)


def get_activation_link(user):
    s = get_serializer()
    payload = s.dumps(user.id)
    return flask.url_for('users.activate_user', payload=payload, _external=True)


def get_password_reset_link(user):
    # This mess to not to have static password reset links
    # Maybe not the best idea? But this should not be a security risk, and it works.
    password_hash_hash = binascii.hexlify(sha1_hash(user.password_hash.hash)).decode()

    s = get_serializer()
    payload = s.dumps((time.time(), password_hash_hash, user.id))
    return flask.url_for('account.password_reset', payload=payload, _external=True)

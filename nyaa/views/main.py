import base64
import math
import re
from datetime import datetime, timedelta
from ipaddress import ip_address

import flask
from flask_paginate import Pagination

from nyaa import models
from nyaa.extensions import db
from nyaa.search import (DEFAULT_MAX_SEARCH_RESULT, DEFAULT_PER_PAGE, SERACH_PAGINATE_DISPLAY_MSG,
                         _generate_query_string, search_db, search_db_baked, search_elastic)
from nyaa.utils import chain_get
from nyaa.views.account import logout

app = flask.current_app
bp = flask.Blueprint('main', __name__)


@bp.app_errorhandler(404)
def not_found(error):
    return flask.render_template('404.html'), 404


@bp.before_app_request
def before_request():
    flask.g.user = None
    if 'user_id' in flask.session:
        user = models.User.by_id(flask.session['user_id'])
        if not user:
            return logout()

        # Logout inactive and banned users
        if user.status != models.UserStatusType.ACTIVE:
            return logout()

        flask.g.user = user

        if 'timeout' not in flask.session or flask.session['timeout'] < datetime.now():
            flask.session['timeout'] = datetime.now() + timedelta(days=7)
            flask.session.permanent = True
            flask.session.modified = True

        if not app.config['MAINTENANCE_MODE']:
            ip = ip_address(flask.request.remote_addr)
            if user.last_login_ip != ip:
                user.last_login_ip = ip.packed
                db.session.add(user)
                db.session.commit()

    # Check if user is banned on POST
    if flask.request.method == 'POST':
        ip = ip_address(flask.request.remote_addr).packed
        banned = models.Ban.banned(None, ip).first()
        if banned:
            if flask.g.user:
                return logout()

            return 'You are banned.', 403


@bp.route('/rss', defaults={'rss': True})
@bp.route('/', defaults={'rss': False})
def home(rss):
    render_as_rss = rss
    req_args = flask.request.args
    if req_args.get('page') == 'rss':
        render_as_rss = True

    search_term = chain_get(req_args, 'q', 'term')

    sort_key = req_args.get('s')
    sort_order = req_args.get('o')

    category = chain_get(req_args, 'c', 'cats')
    quality_filter = chain_get(req_args, 'f', 'filter')

    user_name = chain_get(req_args, 'u', 'user')
    page_number = chain_get(req_args, 'p', 'page', 'offset')
    try:
        page_number = max(1, int(page_number))
    except (ValueError, TypeError):
        page_number = 1

    # Check simply if the key exists
    use_magnet_links = 'magnets' in req_args or 'm' in req_args

    results_per_page = app.config.get('RESULTS_PER_PAGE', DEFAULT_PER_PAGE)

    user_id = None
    if user_name:
        user = models.User.by_username(user_name)
        if not user:
            flask.abort(404)
        user_id = user.id

    special_results = {
        'first_word_user': None,
        'query_sans_user': None,
        'infohash_torrent': None
    }
    # Add advanced features to searches (but not RSS or user searches)
    if search_term and not render_as_rss and not user_id:
        # Check if the first word of the search is an existing user
        user_word_match = re.match(r'^([a-zA-Z0-9_-]+) *(.*|$)', search_term)
        if user_word_match:
            special_results['first_word_user'] = models.User.by_username(user_word_match.group(1))
            special_results['query_sans_user'] = user_word_match.group(2)

        # Check if search is a 40-char torrent hash (or 32-char base32 hash)
        infohash_match = re.match(r'(?i)^([a-f0-9]{40})$', search_term)
        base32_infohash_match = re.match(r'(?i)^([a-z0-9]{32})$', search_term)
        if infohash_match:
            # Check for info hash in database
            matched_torrent = models.Torrent.by_info_hash_hex(infohash_match.group(1))
            special_results['infohash_torrent'] = matched_torrent
        elif base32_infohash_match:
            # Convert base32 to info_hash
            info_hash = base64.b32decode(base32_infohash_match.group(1))
            matched_torrent = models.Torrent.by_info_hash(info_hash)
            special_results['infohash_torrent'] = matched_torrent

    query_args = {
        'user': user_id,
        'sort': sort_key or 'id',
        'order': sort_order or 'desc',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page_number,
        'rss': render_as_rss,
        'per_page': results_per_page
    }

    if flask.g.user:
        query_args['logged_in_user'] = flask.g.user
        if flask.g.user.is_moderator:  # God mode
            query_args['admin'] = True

    infohash_torrent = special_results.get('infohash_torrent')
    if infohash_torrent:
        # infohash_torrent is only set if this is not RSS or userpage search
        flask.flash(flask.Markup('You were redirected here because '
                                 'the given hash matched this torrent.'), 'info')
        # Redirect user from search to the torrent if we found one with the specific info_hash
        return flask.redirect(flask.url_for('torrents.view', torrent_id=infohash_torrent.id))

    # If searching, we get results from elastic search
    use_elastic = app.config.get('USE_ELASTIC_SEARCH')
    if use_elastic and search_term:
        query_args['term'] = search_term

        max_search_results = app.config.get('ES_MAX_SEARCH_RESULT', DEFAULT_MAX_SEARCH_RESULT)

        # Only allow up to (max_search_results / page) pages
        max_page = min(query_args['page'], int(math.ceil(max_search_results / results_per_page)))

        query_args['page'] = max_page
        query_args['max_search_results'] = max_search_results

        query_results = search_elastic(**query_args)

        if render_as_rss:
            return render_rss(
                '"{}"'.format(search_term), query_results,
                use_elastic=True, magnet_links=use_magnet_links)
        else:
            rss_query_string = _generate_query_string(
                search_term, category, quality_filter, user_name)
            max_results = min(max_search_results, query_results['hits']['total']['value'])
            # change p= argument to whatever you change page_parameter to or pagination breaks
            pagination = Pagination(p=query_args['page'], per_page=results_per_page,
                                    total=max_results, bs_version=3, page_parameter='p',
                                    display_msg=SERACH_PAGINATE_DISPLAY_MSG)
            return flask.render_template('home.html',
                                         use_elastic=True,
                                         pagination=pagination,
                                         torrent_query=query_results,
                                         search=query_args,
                                         rss_filter=rss_query_string,
                                         special_results=special_results)
    else:
        # If ES is enabled, default to db search for browsing
        if use_elastic:
            query_args['term'] = ''
        else:  # Otherwise, use db search for everything
            query_args['term'] = search_term or ''

        if app.config['USE_BAKED_SEARCH']:
            query = search_db_baked(**query_args)
        else:
            query = search_db(**query_args)

        if render_as_rss:
            return render_rss('Home', query, use_elastic=False, magnet_links=use_magnet_links)
        else:
            rss_query_string = _generate_query_string(
                search_term, category, quality_filter, user_name)
            # Use elastic is always false here because we only hit this section
            # if we're browsing without a search term (which means we default to DB)
            # or if ES is disabled
            return flask.render_template('home.html',
                                         use_elastic=False,
                                         torrent_query=query,
                                         search=query_args,
                                         rss_filter=rss_query_string,
                                         special_results=special_results)


def render_rss(label, query, use_elastic, magnet_links=False):
    rss_xml = flask.render_template('rss.xml',
                                    use_elastic=use_elastic,
                                    magnet_links=magnet_links,
                                    term=label,
                                    site_url=flask.request.url_root,
                                    torrent_query=query)
    response = flask.make_response(rss_xml)
    response.headers['Content-Type'] = 'application/xml'
    # Cache for an hour
    response.headers['Cache-Control'] = 'max-age={}'.format(1 * 5 * 60)
    return response

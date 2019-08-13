import functools
import os.path
import re
from datetime import datetime
from email.utils import formatdate

import flask
from werkzeug.urls import url_encode

from nyaa.backend import get_category_id_map
from nyaa.torrents import create_magnet

app = flask.current_app
bp = flask.Blueprint('template-utils', __name__)
_static_cache = {}  # For static_cachebuster


# ######################## CONTEXT PROCESSORS ########################

# For processing ES links
@bp.app_context_processor
def create_magnet_from_es_torrent():
    # Since ES entries look like ducks, we can use the create_magnet as-is
    return dict(create_magnet_from_es_torrent=create_magnet)


# ######################### TEMPLATE GLOBALS #########################

flask_url_for = flask.url_for


@functools.lru_cache(maxsize=1024 * 4)
def _caching_url_for(endpoint, **values):
    return flask_url_for(endpoint, **values)


@bp.app_template_global()
def caching_url_for(*args, **kwargs):
    try:
        # lru_cache requires the arguments to be hashable.
        # Majority of the time, they are! But there are some small edge-cases,
        # like our copypasted pagination, parameters can be lists.
        # Attempt caching first:
        return _caching_url_for(*args, **kwargs)
    except TypeError:
        # Then fall back to the original url_for.
        # We could convert the lists to tuples, but the savings are marginal.
        return flask_url_for(*args, **kwargs)


@bp.app_template_global()
def static_cachebuster(filename):
    """ Adds a ?t=<mtime> cachebuster to the given path, if the file exists.
        Results are cached in memory and persist until app restart! """
    # Instead of timestamps, we could use commit hashes (we already load it in __init__)
    # But that'd mean every static resource would get cache busted. This lets unchanged items
    # stay in the cache.

    if app.debug:
        # Do not bust cache on debug (helps debugging)
        return flask.url_for('static', filename=filename)

    # Get file mtime if not already cached.
    if filename not in _static_cache:
        file_path = os.path.join(app.static_folder, filename)
        file_mtime = None
        if os.path.exists(file_path):
            file_mtime = int(os.path.getmtime(file_path))

        _static_cache[filename] = file_mtime

    return flask.url_for('static', filename=filename, t=_static_cache[filename])


@bp.app_template_global()
def modify_query(**new_values):
    args = flask.request.args.copy()

    args.pop('p', None)

    for key, value in new_values.items():
        args[key] = value

    return '{}?{}'.format(flask.request.path, url_encode(args))


@bp.app_template_global()
def filter_truthy(input_list):
    """ Jinja2 can't into list comprehension so this is for
        the search_results.html template """
    return [item for item in input_list if item]


@bp.app_template_global()
def category_name(cat_id):
    """ Given a category id (eg. 1_2), returns a category name (eg. Anime - English-translated) """
    return ' - '.join(get_category_id_map().get(cat_id, ['???']))


# ######################### TEMPLATE FILTERS #########################

@bp.app_template_filter('utc_time')
def get_utc_timestamp(datetime_str):
    """ Returns a UTC POSIX timestamp, as seconds """
    UTC_EPOCH = datetime.utcfromtimestamp(0)
    return int((datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S') - UTC_EPOCH).total_seconds())


@bp.app_template_filter('utc_timestamp')
def get_utc_timestamp_seconds(datetime_instance):
    """ Returns a UTC POSIX timestamp, as seconds """
    UTC_EPOCH = datetime.utcfromtimestamp(0)
    return int((datetime_instance - UTC_EPOCH).total_seconds())


@bp.app_template_filter('display_time')
def get_display_time(datetime_str):
    return datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M')


@bp.app_template_filter('rfc822')
def _jinja2_filter_rfc822(date, fmt=None):
    return formatdate(date.timestamp())


@bp.app_template_filter('rfc822_es')
def _jinja2_filter_rfc822_es(datestr, fmt=None):
    return formatdate(datetime.strptime(datestr, '%Y-%m-%dT%H:%M:%S').timestamp())


@bp.app_template_filter()
def timesince(dt, default='just now'):
    """
    Returns string representing "time since" e.g.
    3 minutes ago, 5 hours ago etc.
    Date and time (UTC) are returned if older than 1 day.
    """

    now = datetime.utcnow()
    diff = now - dt

    periods = (
        (diff.days, 'day', 'days'),
        (diff.seconds / 3600, 'hour', 'hours'),
        (diff.seconds / 60, 'minute', 'minutes'),
        (diff.seconds, 'second', 'seconds'),
    )

    if diff.days >= 1:
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    else:
        for period, singular, plural in periods:

            if period >= 1:
                return '%d %s ago' % (period, singular if int(period) == 1 else plural)

    return default


@bp.app_template_filter()
def regex_replace(s, find, replace):
    """A non-optimal implementation of a regex filter"""
    return re.sub(find, replace, s)

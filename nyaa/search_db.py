import flask
import re
import math
import json
import shlex
from datetime import datetime, timedelta

from nyaa import app, db
from nyaa import models, torrents

from sqlalchemy import or_, and_
import sqlalchemy_fulltext.modes as FullTextMode
from sqlalchemy_fulltext import FullTextSearch


def get_db_sort(sort_by, sort_order):
    db_sort_keys = {
        'id': models.Torrent.id,
        'size': models.Torrent.filesize,
        # Disable this because we disabled this in search_elastic, for the sake of consistency:
        # 'name': models.Torrent.display_name,
        'seeders': models.Statistic.seed_count,
        'leechers': models.Statistic.leech_count,
        'downloads': models.Statistic.download_count
    }
    if not sort_order in ['asc', 'desc']:
        app.logger.warn('sort order {} unsupported'.format(sort_order))
        flask.abort(400)
    try:
        db_sort_key = db_sort_keys[sort_by.lower()]
    except KeyError:
        app.logger.warn('sort by {} unsupported'.format(sort_by))
        flask.abort(400)
    else:
        return db_sort_key

def get_db_tags_filter(include_tags, exclude_tags):
    db_tags = {
        'remake': models.TorrentFlags.REMAKE,
        'complete': models.TorrentFlags.COMPLETE,
        'anonymous': models.TorrentFlags.ANONYMOUS
    }
    flags_mask = 0
    flags_value = 0
    for tag in include_tags:
        try:
            key = db_tags[tag]
        except KeyError:
            app.logger.warn('include tag {} unsupported'.format(tag))
            flask.abort(400)
        else:
            flags_mask |= int(key)
            flags_value |= int(key)
    for tag in exclude_tags:
        try:
            key = db_tags[tag]
        except KeyError:
            app.logger.warn('exclude tag {} unsupported'.format(tag))
            flask.abort(400)
        else:
            flags_mask |= int(key)
    return (flags_mask, flags_value)


def search_db(term='', uploader_id=None,
              categories=None, include_tags=None, exclude_tags=None,
              sort_by='id', sort_order='desc', page=0, page_size=75,
              logged_in_user_id=None, is_admin=False,
              include_total=False):

    if term:
        query = db.session.query(models.TorrentNameSearch)
    else:
        query = models.Torrent.query

    if categories:
        cat_filters = []
        for category in categories:
            main_cat = int(category / 100)
            sub_cat = int(category % 100)
            if sub_cat:
                cat_filters.append(and_(models.Torrent.main_category_id == main_cat,
                                        models.Torrent.sub_category_id == sub_cat))
            else:
                cat_filters.append(models.Torrent.main_category_id == main_cat)
        query = query.filter(or_(*cat_filters))

    (flags_mask, flags_value) = get_db_tags_filter(include_tags, exclude_tags)

    if uploader_id:
        # View only torrents uploaded by a specific user
        query = query.filter(models.Torrent.uploader_id == uploader_id)
        if not is_admin:
            if not uploader_id == logged_in_user_id:
                # Hide all HIDDEN and ANONYMOUS torrents if the user isn't searching his own history
                if 'anonymous' in include_tags:
                    raise EmptySearchError('Cannot search for anonymous posts of a single user')
                flags_mask |= int(models.TorrentFlags.HIDDEN | models.TorrentFlags.ANONYMOUS)
    else:
        if not is_admin:
            if logged_in_user_id:
                # Hide all HIDDEN torrents unless it was uploaded the logged in user
                query = query.filter(
                    (models.Torrent.flags.op('&')(int(models.TorrentFlags.HIDDEN)).is_(False)) |
                    (models.Torrent.uploader_id == logged_in_user_id))
            else:
                flags_mask |= int(models.TorrentFlags.HIDDEN)

    if flags_mask:
        query.filter(models.Torrent.flags.op('&')(flags_mask).is_(flags_value))

    if term:
        for item in shlex.split(term, posix=False):
            if len(item) >= 2:
                query = query.filter(FullTextSearch(
                    item, models.TorrentNameSearch, FullTextMode.NATURAL))

    db_sort = get_db_sort(sort_by, sort_order)
    # Sort and order
    if db_sort.class_ != models.Torrent:
        query = query.join(db_sort.class_)
    query = query.order_by(getattr(db_sort, sort_order)())

    if not include_total:
        return query.paginate_faste(page, page_size, step=0)
    else:
        return query.paginate_faste(page, page_size)

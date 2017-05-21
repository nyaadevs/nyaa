import flask
import re
import math
import json
import shlex
from datetime import datetime, timedelta

from nyaa import app, db
from nyaa import models, torrents
from nyaa.search_elastic import search_elastic
from nyaa.search_db import search_db

class EmptySearchError(Exception):
    """Indicates that the query is guaranteed to produce an empty result"""
    pass

class EmptySearchResult:
    def __init__(self):
        self.total = 0

    def __len__(self):
        return 0

    def __getitem__(self, i):
        raise StopIteration

def search_custom(term='', uploader_id=None,
                  categories=None, include_tags=None, exclude_tags=None,
                  sort_by='id', sort_order='desc', page=0, page_size=75,
                  logged_in_user_id=None, is_admin=False,
                  include_total=False):
    
    query_args = {
        'term': term,
        'uploader_id': uploader_id,
        'categories': categories,
        'include_tags': include_tags,
        'exclude_tags': exclude_tags,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'page': page,
        'page_size': page_size,
        'logged_in_user_id': logged_in_user_id,
        'is_admin': is_admin,
        'include_total': include_total
    }

    use_elastic = app.config.get('USE_ELASTIC_SEARCH')
    if use_elastic and term:
        query_args['max_search_results'] = app.config.get('ES_MAX_SEARCH_RESULT', 1000)
        result = search_elastic(**query_args)
        return result
    else:
        result = search_db(**query_args)
        return result

def get_search_categories(category):
    cat_match = re.match(r'^(\d+)_(\d+)$', category)
    if cat_match:
        category = int(cat_match.group(1)) * 100 + int(cat_match.group(2))
    else:
        category = int(category)
    if category:
        return [category]
    else:
        return []

def get_filter_tags(quality_filter):
    filter_keys = {
        '0': ([], []),
        '1': ([], ['remake']),
        '2': (['trusted'], []),
        '3': (['complete'], [])
    }
    try:
        return filter_keys[quality_filter]
    except KeyError:
        app.logger.warn('filter mode {} unsupported'.format(quality_filter))
        flask.abort(400)

# Legacy search, has knowledge about 'rss'.
def search(term='', user=None, sort='id', order='desc', category='0_0',
           quality_filter='0', page=1, rss=False, admin=False,
           logged_in_user=None, per_page=75):

    app.logger.info('Searching db for term={} category={} page={}'.format(term, category, page))

    (include_tags, exclude_tags) = get_filter_tags(quality_filter)

    categories = get_search_categories(category)

    query_args = {
        'term': term,
        'uploader_id': user,
        'categories': categories,
        'include_tags': include_tags,
        'exclude_tags': exclude_tags,
        'sort_by': sort,
        'sort_order': order,
        'page': page,
        'page_size': per_page,
        'logged_in_user_id': logged_in_user.id if logged_in_user else None,
        'is_admin': admin,
        'include_total': True
    }

    # Restrict rss feed
    if rss:
        query_args['sort_by'] = 'id'
        query_args['sort_order'] = 'desc'
        query_args['logged_in_user_id'] = None
        query_args['include_total'] = False

    result = search_custom(**query_args)
    return result


import math
import re
import shlex
import threading
import time

import flask
from flask_sqlalchemy import Pagination

import sqlalchemy
import sqlalchemy_fulltext.modes as FullTextMode
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, Search
from sqlalchemy.ext import baked
from sqlalchemy_fulltext import FullTextSearch

from nyaa import models
from nyaa.extensions import db

app = flask.current_app

DEFAULT_MAX_SEARCH_RESULT = 1000
DEFAULT_PER_PAGE = 75
SERACH_PAGINATE_DISPLAY_MSG = ('Displaying results {start}-{end} out of {total} results.<br>\n'
                               'Please refine your search results if you can\'t find '
                               'what you were looking for.')

# Table-column index name cache for _get_index_name
# In format of {'table' : {'column_a':'ix_table_column_a'}}
_index_name_cache = {}


def _get_index_name(column):
    ''' Returns an index name for a given column, or None.
        Only considers single-column indexes.
        Results are cached in memory (until app restart). '''
    column_table_name = column.class_.__table__.name
    table_indexes = _index_name_cache.get(column_table_name)
    if table_indexes is None:
        # Load the real table schema from the database
        # Fresh MetaData used to skip SQA's cache and get the real indexes on the database
        table_indexes = {}
        try:
            column_table = sqlalchemy.Table(column_table_name,
                                            sqlalchemy.MetaData(),
                                            autoload=True, autoload_with=db.engine)
        except sqlalchemy.exc.NoSuchTableError:
            # Trust the developer to notice this?
            pass
        else:
            for index in column_table.indexes:
                # Only consider indexes with one column
                if len(index.expressions) > 1:
                    continue

                index_column = index.expressions[0]
                table_indexes[index_column.name] = index.name
        _index_name_cache[column_table_name] = table_indexes

    return table_indexes.get(column.name)


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


# For preprocessing ES search terms in _parse_es_search_terms
QUOTED_LITERAL_REGEX = re.compile(r'(?i)(-)?"(.+?)"')
QUOTED_LITERAL_GROUP_REGEX = re.compile(r'''
    (?i)
    (-)? # Negate entire group at once
    (
        ".+?" # First literal
        (?:
            \|    # OR
            ".+?" # Second literal
        )+        # repeating
    )
    ''', re.X)


def _es_name_exact_phrase(literal):
    ''' Returns a Query for a phrase match on the display_name for a given literal '''
    return Q({
        'match_phrase': {
            'display_name.exact': {
                'query': literal,
                'analyzer': 'exact_analyzer'
            }
        }
    })


def _parse_es_search_terms(search, search_terms):
    ''' Parse search terms into a query with properly handled literal phrases
        (the simple_query_string is not so great with exact results).
        For example:
            foo bar "hello world" -"exclude this"
        will become a must simple_query_string for "foo bar", a must phrase_match for
        "hello world" and a must_not for "exclude this".
        Returns the search with the generated bool-query added to it. '''

    # Literal must and must-not sets
    must_set = set()
    must_not_set = set()

    must_or_groups = []
    must_not_or_groups = []

    def must_group_matcher(match):
        ''' Grabs [-]"foo"|"bar"[|"baz"...] groups from the search terms '''
        negated = bool(match.group(1))
        literal_group = match.group(2)

        literals = QUOTED_LITERAL_REGEX.findall(literal_group)
        group_query = Q(
            'bool',
            should=[_es_name_exact_phrase(lit_m[1]) for lit_m in literals]
        )

        if negated:
            must_not_or_groups.append(group_query)
        else:
            must_or_groups.append(group_query)

        # Remove the parsed group from search terms
        return ''

    def must_matcher(match):
        ''' Grabs [-]"foo" literals from the search terms '''
        negated = bool(match.group(1))
        literal = match.group(2)

        if negated:
            must_not_set.add(literal)
        else:
            must_set.add(literal)

        # Remove the parsed literal from search terms
        return ''

    # Remove quoted parts (optionally prepended with -) and store them in the sets
    parsed_search_terms = QUOTED_LITERAL_GROUP_REGEX.sub(must_group_matcher, search_terms).strip()
    parsed_search_terms = QUOTED_LITERAL_REGEX.sub(must_matcher, parsed_search_terms).strip()

    # Create phrase matches (if any)
    must_queries = [_es_name_exact_phrase(lit) for lit in must_set] + must_or_groups
    must_not_queries = [_es_name_exact_phrase(lit) for lit in must_not_set] + must_not_or_groups

    if parsed_search_terms:
        # Normal text search without the quoted parts
        must_queries.append(
            Q(
                'simple_query_string',
                # Query both fields, latter for words with >15 chars
                fields=['display_name', 'display_name.fullword'],
                analyzer='my_search_analyzer',
                default_operator="AND",
                query=parsed_search_terms
            )
        )

    if must_queries or must_not_queries:
        # Create a combined Query with the positive and negative matches
        combined_search_query = Q(
            'bool',
            must=must_queries,
            must_not=must_not_queries
        )
        search = search.query(combined_search_query)

    return search


def search_elastic(term='', user=None, sort='id', order='desc',
                   category='0_0', quality_filter='0', page=1,
                   rss=False, admin=False, logged_in_user=None,
                   per_page=75, max_search_results=1000):
    # This function can easily be memcached now
    if page > 4294967295:
        flask.abort(404)

    es_client = Elasticsearch(hosts=app.config['ES_HOSTS'])

    es_sort_keys = {
        'id': 'id',
        'size': 'filesize',
        # 'name': 'display_name',  # This is slow and buggy
        'comments': 'comment_count',
        'seeders': 'seed_count',
        'leechers': 'leech_count',
        'downloads': 'download_count'
    }

    sort_ = sort.lower()
    if sort_ not in es_sort_keys:
        flask.abort(400)

    es_sort = es_sort_keys[sort]

    order_keys = {
        'desc': 'desc',
        'asc': 'asc'
    }

    order_ = order.lower()
    if order_ not in order_keys:
        flask.abort(400)

    # Only allow ID, desc if RSS
    if rss:
        sort = es_sort_keys['id']
        order = 'desc'

    # funky, es sort is default asc, prefixed by '-' if desc
    if 'desc' == order:
        es_sort = '-' + es_sort

    # Quality filter
    quality_keys = [
        '0',  # Show all
        '1',  # No remakes
        '2',  # Only trusted
        '3'   # Only completed
    ]

    if quality_filter.lower() not in quality_keys:
        flask.abort(400)

    quality_filter = int(quality_filter)

    # Category filter
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
                if not sub_category:
                    flask.abort(400)
            else:
                main_category = models.MainCategory.by_id(main_cat_id)
                if not main_category:
                    flask.abort(400)

    # This might be useless since we validate users
    # before coming into this method, but just to be safe...
    if user:
        user = models.User.by_id(user)
        if not user:
            flask.abort(404)
        user = user.id

    same_user = False
    if logged_in_user:
        same_user = user == logged_in_user.id

    s = Search(using=es_client, index=app.config.get('ES_INDEX_NAME'))  # todo, sukebei prefix

    # Apply search term
    if term:
        # Do some preprocessing on the search terms for literal "" matching
        s = _parse_es_search_terms(s, term)

    # User view (/user/username)
    if user:
        s = s.filter('term', uploader_id=user)

        if not admin:
            # Hide all DELETED torrents if regular user
            s = s.filter('term', deleted=False)
            # If logged in user is not the same as the user being viewed,
            # show only torrents that aren't hidden or anonymous.
            #
            # If logged in user is the same as the user being viewed,
            # show all torrents including hidden and anonymous ones.
            #
            # On RSS pages in user view, show only torrents that
            # aren't hidden or anonymous no matter what
            if not same_user or rss:
                s = s.filter('term', hidden=False)
                s = s.filter('term', anonymous=False)
    # General view (homepage, general search view)
    else:
        if not admin:
            # Hide all DELETED torrents if regular user
            s = s.filter('term', deleted=False)
            # If logged in, show all torrents that aren't hidden unless they belong to you
            # On RSS pages, show all public torrents and nothing more.
            if logged_in_user and not rss:
                hiddenFilter = Q('term', hidden=False)
                userFilter = Q('term', uploader_id=logged_in_user.id)
                combinedFilter = hiddenFilter | userFilter
                s = s.filter('bool', filter=[combinedFilter])
            else:
                s = s.filter('term', hidden=False)

    if main_category:
        s = s.filter('term', main_category_id=main_cat_id)
    elif sub_category:
        s = s.filter('term', main_category_id=main_cat_id)
        s = s.filter('term', sub_category_id=sub_cat_id)

    if quality_filter == 0:
        pass
    elif quality_filter == 1:
        s = s.filter('term', remake=False)
    elif quality_filter == 2:
        s = s.filter('term', trusted=True)
    elif quality_filter == 3:
        s = s.filter('term', complete=True)

    # Apply sort
    s = s.sort(es_sort)

    # Only show first RESULTS_PER_PAGE items for RSS
    if rss:
        s = s[0:per_page]
    else:
        max_page = min(page, int(math.ceil(max_search_results / float(per_page))))
        from_idx = (max_page - 1) * per_page
        to_idx = min(max_search_results, max_page * per_page)
        s = s[from_idx:to_idx]

    highlight = app.config.get('ENABLE_ELASTIC_SEARCH_HIGHLIGHT')
    if highlight:
        s = s.highlight_options(tags_schema='styled')
        s = s.highlight("display_name")

    # Return query, uncomment print line to debug query
    # from pprint import pprint
    # print(json.dumps(s.to_dict()))
    return s.execute()


class QueryPairCaller(object):
    ''' Simple stupid class to filter one or more queries with the same args '''

    def __init__(self, *items):
        self.items = list(items)

    def __getattr__(self, name):
        # Create and return a wrapper that will call item.foobar(*args, **kwargs) for all items
        def wrapper(*args, **kwargs):
            for i in range(len(self.items)):
                method = getattr(self.items[i], name)
                if not callable(method):
                    raise Exception('Attribute %r is not callable' % method)
                self.items[i] = method(*args, **kwargs)
            return self

        return wrapper


def search_db(term='', user=None, sort='id', order='desc', category='0_0',
              quality_filter='0', page=1, rss=False, admin=False,
              logged_in_user=None, per_page=75):
    if page > 4294967295:
        flask.abort(404)

    MAX_PAGES = app.config.get("MAX_PAGES", 0)

    same_user = False
    if logged_in_user:
        same_user = logged_in_user.id == user

    # Logged in users should always be able to view their full listing.
    if same_user or admin:
        MAX_PAGES = 0

    if MAX_PAGES and page > MAX_PAGES:
        flask.abort(flask.Response("You've exceeded the maximum number of pages. Please "
                                   "make your search query less broad.", 403))

    sort_keys = {
        'id': models.Torrent.id,
        'size': models.Torrent.filesize,
        # Disable this because we disabled this in search_elastic, for the sake of consistency:
        # 'name': models.Torrent.display_name,
        'comments': models.Torrent.comment_count,
        'seeders': models.Statistic.seed_count,
        'leechers': models.Statistic.leech_count,
        'downloads': models.Statistic.download_count
    }

    sort_column = sort_keys.get(sort.lower())
    if sort_column is None:
        flask.abort(400)

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
        sort_column = sort_keys['id']
        order = 'desc'

    model_class = models.TorrentNameSearch if term else models.Torrent

    query = db.session.query(model_class)

    # This is... eh. Optimize the COUNT() query since MySQL is bad at that.
    # See http://docs.sqlalchemy.org/en/rel_1_1/orm/query.html#sqlalchemy.orm.query.Query.count
    # Wrap the queries into the helper class to deduplicate code and apply filters to both in one go
    count_query = db.session.query(sqlalchemy.func.count(model_class.id))
    qpc = QueryPairCaller(query, count_query)

    # User view (/user/username)
    if user:
        qpc.filter(models.Torrent.uploader_id == user)

        if not admin:
            # Hide all DELETED torrents if regular user
            qpc.filter(models.Torrent.flags.op('&')(
                int(models.TorrentFlags.DELETED)).is_(False))
            # If logged in user is not the same as the user being viewed,
            # show only torrents that aren't hidden or anonymous
            #
            # If logged in user is the same as the user being viewed,
            # show all torrents including hidden and anonymous ones
            #
            # On RSS pages in user view,
            # show only torrents that aren't hidden or anonymous no matter what
            if not same_user or rss:
                qpc.filter(models.Torrent.flags.op('&')(
                    int(models.TorrentFlags.HIDDEN | models.TorrentFlags.ANONYMOUS)).is_(False))
    # General view (homepage, general search view)
    else:
        if not admin:
            # Hide all DELETED torrents if regular user
            qpc.filter(models.Torrent.flags.op('&')(
                int(models.TorrentFlags.DELETED)).is_(False))
            # If logged in, show all torrents that aren't hidden unless they belong to you
            # On RSS pages, show all public torrents and nothing more.
            if logged_in_user and not rss:
                qpc.filter(
                    (models.Torrent.flags.op('&')(int(models.TorrentFlags.HIDDEN)).is_(False)) |
                    (models.Torrent.uploader_id == logged_in_user.id))
            # Otherwise, show all torrents that aren't hidden
            else:
                qpc.filter(models.Torrent.flags.op('&')(
                    int(models.TorrentFlags.HIDDEN)).is_(False))

    if main_category:
        qpc.filter(models.Torrent.main_category_id == main_cat_id)
    elif sub_category:
        qpc.filter((models.Torrent.main_category_id == main_cat_id) &
                   (models.Torrent.sub_category_id == sub_cat_id))

    if filter_tuple:
        qpc.filter(models.Torrent.flags.op('&')(
            int(filter_tuple[0])).is_(filter_tuple[1]))

    if term:
        for item in shlex.split(term, posix=False):
            if len(item) >= 2:
                qpc.filter(FullTextSearch(
                    item, models.TorrentNameSearch, FullTextMode.NATURAL))
    query, count_query = qpc.items
    # Sort and order
    if sort_column.class_ != models.Torrent:
        index_name = _get_index_name(sort_column)
        query = query.join(sort_column.class_)
        query = query.with_hint(sort_column.class_, 'USE INDEX ({0})'.format(index_name))

    query = query.order_by(getattr(sort_column, order)())

    if rss:
        query = query.limit(per_page)
    else:
        query = query.paginate_faste(page, per_page=per_page, step=5, count_query=count_query,
                                     max_page=MAX_PAGES)

    return query


# Baked queries follow

class BakedPair(object):
    def __init__(self, *items):
        self.items = list(items)

    def __iadd__(self, other):
        for item in self.items:
            item += other

        return self


bakery = baked.bakery()


BAKED_SORT_KEYS = {
    'id': models.Torrent.id,
    'size': models.Torrent.filesize,
    'comments': models.Torrent.comment_count,
    'seeders': models.Statistic.seed_count,
    'leechers': models.Statistic.leech_count,
    'downloads': models.Statistic.download_count
}

BAKED_SORT_LAMBDAS = {
    'id-asc': lambda q: q.order_by(models.Torrent.id.asc()),
    'id-desc': lambda q: q.order_by(models.Torrent.id.desc()),

    'size-asc': lambda q: q.order_by(models.Torrent.filesize.asc()),
    'size-desc': lambda q: q.order_by(models.Torrent.filesize.desc()),

    'comments-asc': lambda q: q.order_by(models.Torrent.comment_count.asc()),
    'comments-desc': lambda q: q.order_by(models.Torrent.comment_count.desc()),

    # This is a bit stupid, but programmatically generating these mixed up the baked keys, so deal.
    'seeders-asc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_seed_count)'
    ).order_by(models.Statistic.seed_count.asc(),  models.Torrent.id.asc()),
    'seeders-desc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_seed_count)'
    ).order_by(models.Statistic.seed_count.desc(), models.Torrent.id.desc()),

    'leechers-asc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_leech_count)'
    ).order_by(models.Statistic.leech_count.asc(),  models.Torrent.id.asc()),
    'leechers-desc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_leech_count)'
    ).order_by(models.Statistic.leech_count.desc(), models.Torrent.id.desc()),

    'downloads-asc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_download_count)'
    ).order_by(models.Statistic.download_count.asc(),  models.Torrent.id.asc()),
    'downloads-desc': lambda q: q.join(models.Statistic).with_hint(
        models.Statistic, 'USE INDEX (idx_nyaa_statistics_download_count)'
    ).order_by(models.Statistic.download_count.desc(), models.Torrent.id.desc()),
}


BAKED_FILTER_LAMBDAS = {
    '0': None,
    '1': lambda q: (
        q.filter(models.Torrent.flags.op('&')(models.TorrentFlags.REMAKE.value).is_(False))
    ),
    '2': lambda q: (
        q.filter(models.Torrent.flags.op('&')(models.TorrentFlags.TRUSTED.value).is_(True))
    ),
    '3': lambda q: (
        q.filter(models.Torrent.flags.op('&')(models.TorrentFlags.COMPLETE.value).is_(True))
    ),
}


def search_db_baked(term='', user=None, sort='id', order='desc', category='0_0',
                    quality_filter='0', page=1, rss=False, admin=False,
                    logged_in_user=None, per_page=75):
    if page > 4294967295:
        flask.abort(404)

    MAX_PAGES = app.config.get("MAX_PAGES", 0)

    if MAX_PAGES and page > MAX_PAGES:
        flask.abort(flask.Response("You've exceeded the maximum number of pages. Please "
                                   "make your search query less broad.", 403))

    sort_lambda = BAKED_SORT_LAMBDAS.get('{}-{}'.format(sort, order).lower())
    if not sort_lambda:
        flask.abort(400)

    sentinel = object()
    filter_lambda = BAKED_FILTER_LAMBDAS.get(quality_filter.lower(), sentinel)
    if filter_lambda is sentinel:
        flask.abort(400)

    if user:
        user = models.User.by_id(user)
        if not user:
            flask.abort(404)
        user = user.id

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
                if not sub_category:
                    flask.abort(400)
            else:
                main_category = models.MainCategory.by_id(main_cat_id)
                if not main_category:
                    flask.abort(400)

    # Force sort by id desc if rss
    if rss:
        sort_lambda = BAKED_SORT_LAMBDAS['id-desc']

    same_user = False
    if logged_in_user:
        same_user = logged_in_user.id == user

    if term:
        query = bakery(lambda session: session.query(models.TorrentNameSearch))
        count_query = bakery(lambda session: session.query(
            sqlalchemy.func.count(models.TorrentNameSearch.id)))
    else:
        query = bakery(lambda session: session.query(models.Torrent))
        # This is... eh. Optimize the COUNT() query since MySQL is bad at that.
        # See http://docs.sqlalchemy.org/en/rel_1_1/orm/query.html#sqlalchemy.orm.query.Query.count
        # Wrap the queries into the helper class to deduplicate code and
        # apply filters to both in one go
        count_query = bakery(lambda session: session.query(
            sqlalchemy.func.count(models.Torrent.id)))

    qpc = BakedPair(query, count_query)
    bp = sqlalchemy.bindparam

    baked_params = {}

    # User view (/user/username)
    if user:
        qpc += lambda q: q.filter(models.Torrent.uploader_id == bp('user'))
        baked_params['user'] = user

        if not admin:
            # Hide all DELETED torrents if regular user
            qpc += lambda q: q.filter(models.Torrent.flags.op('&')
                                      (int(models.TorrentFlags.DELETED)).is_(False))
            # If logged in user is not the same as the user being viewed,
            # show only torrents that aren't hidden or anonymous
            #
            # If logged in user is the same as the user being viewed,
            # show all torrents including hidden and anonymous ones
            #
            # On RSS pages in user view,
            # show only torrents that aren't hidden or anonymous no matter what
            if not same_user or rss:
                qpc += lambda q: (
                    q.filter(
                        models.Torrent.flags.op('&')(
                            int(models.TorrentFlags.HIDDEN | models.TorrentFlags.ANONYMOUS)
                        ).is_(False)
                    )
                )
    # General view (homepage, general search view)
    else:
        if not admin:
            # Hide all DELETED torrents if regular user
            qpc += lambda q: q.filter(models.Torrent.flags.op('&')
                                      (int(models.TorrentFlags.DELETED)).is_(False))
            # If logged in, show all torrents that aren't hidden unless they belong to you
            # On RSS pages, show all public torrents and nothing more.
            if logged_in_user and not rss:
                qpc += lambda q: q.filter(
                    (models.Torrent.flags.op('&')(int(models.TorrentFlags.HIDDEN)).is_(False)) |
                    (models.Torrent.uploader_id == bp('logged_in_user'))
                )
                baked_params['logged_in_user'] = logged_in_user
            # Otherwise, show all torrents that aren't hidden
            else:
                qpc += lambda q: q.filter(models.Torrent.flags.op('&')
                                          (int(models.TorrentFlags.HIDDEN)).is_(False))

    if sub_cat_id:
        qpc += lambda q: q.filter(
            (models.Torrent.main_category_id == bp('main_cat_id')),
            (models.Torrent.sub_category_id == bp('sub_cat_id'))
        )
        baked_params['main_cat_id'] = main_cat_id
        baked_params['sub_cat_id'] = sub_cat_id
    elif main_cat_id:
        qpc += lambda q: q.filter(models.Torrent.main_category_id == bp('main_cat_id'))
        baked_params['main_cat_id'] = main_cat_id

    if filter_lambda:
        qpc += filter_lambda

    if term:
        raise Exception('Baked search does not support search terms')

    # Sort and order
    query += sort_lambda

    if rss:
        query += lambda q: q.limit(bp('per_page'))
        baked_params['per_page'] = per_page

        return query(db.session()).params(**baked_params).all()

    return baked_paginate(query, count_query, baked_params,
                          page, per_page=per_page, step=5, max_page=MAX_PAGES)


class ShoddyLRU(object):
    def __init__(self, max_entries=128, expiry=60):
        self.max_entries = max_entries
        self.expiry = expiry

        # Contains [value, last_used, expires_at]
        self.entries = {}
        self._lock = threading.Lock()

        self._sentinel = object()

    def get(self, key, default=None):
        entry = self.entries.get(key)
        if entry is None:
            return default

        now = time.time()
        if now > entry[2]:
            with self._lock:
                del self.entries[key]
            return default

        entry[1] = now
        return entry[0]

    def put(self, key, value, expiry=None):
        with self._lock:
            overflow = len(self.entries) - self.max_entries
            if overflow > 0:
                # Pick the least recently used keys
                removed_keys = [key for key, value in sorted(
                    self.entries.items(), key=lambda t:t[1][1])][:overflow]
                for key in removed_keys:
                    del self.entries[key]

            now = time.time()
            self.entries[key] = [value, now, now + (expiry or self.expiry)]


LRU_CACHE = ShoddyLRU(256, 60)


def baked_paginate(query, count_query, params, page=1, per_page=50, max_page=None, step=5):
    if page < 1:
        flask.abort(404)

    if max_page and page > max_page:
        flask.abort(404)
    bp = sqlalchemy.bindparam

    ses = db.session()

    # Count all items, use cache
    if app.config['COUNT_CACHE_DURATION']:
        query_key = (count_query._effective_key(ses), tuple(sorted(params.items())))
        total_query_count = LRU_CACHE.get(query_key)
        if total_query_count is None:
            total_query_count = count_query(ses).params(**params).scalar()
            LRU_CACHE.put(query_key, total_query_count, expiry=app.config['COUNT_CACHE_DURATION'])
    else:
        total_query_count = count_query(ses).params(**params).scalar()

    # Grab items on current page
    query += lambda q: q.limit(bp('limit')).offset(bp('offset'))
    params['limit'] = per_page
    params['offset'] = (page - 1) * per_page

    res = query(ses).params(**params)
    items = res.all()

    if max_page:
        total_query_count = min(total_query_count, max_page * per_page)

    # Handle case where we've had no results but then have some while in cache
    total_query_count = max(total_query_count, len(items))

    if not items and page != 1:
        flask.abort(404)

    return Pagination(None, page, per_page, total_query_count, items)

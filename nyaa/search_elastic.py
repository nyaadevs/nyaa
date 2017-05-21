import flask
import re
import math
import json
import shlex
import logging

from datetime import datetime, timedelta
from werkzeug.utils import cached_property

from nyaa import app, db
from nyaa import models, torrents

from flask_sqlalchemy import Pagination
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search, Q

class ElasticItemStats:
    def __init__(self, elasticResult):
        self.seed_count = elasticResult.seed_count
        self.leech_count = elasticResult.leech_count
        self.download_count = elasticResult.download_count

class ElasticItem:
    passtru_attributes = ['id', 'has_torrent', 'display_name', 'filesize',
                          'uploader_id', 'main_category_id', 'sub_category_id',
                          'anonymous', 'trusted', 'remake', 'complete', 'hidden', 'deleted']

    def __init__(self, elasticResult):
        self.elastic = elasticResult
        self.created_time = datetime.strptime(self.elastic.created_time, '%Y-%m-%dT%H:%M:%S')
        self.created_utc_timestamp = (self.created_time - models.UTC_EPOCH).total_seconds()
        self.info_hash = bytes.fromhex(self.elastic.info_hash)
        # TODO: Verify if models.SubCategory is cached or hits the db on every call
        self.stats = ElasticItemStats(self.elastic)

    def __getattr__(self, name):
        try:
            result = self.elastic[name]
        except KeyError:
            # Raise an AttributeError if the key does not exist
            raise AttributeError('{class_name!r} object has no attribute {attr!r}'
                                 .format(class_name=self.__class__.__name__, attr=name)
                                )
        else:
            if name not in self.passtru_attributes:
                app.logger.warn('{class_name!r} object accessing unsupported attribute {attr!r}'
                              .format(class_name=self.__class__.__name__, attr=name)
                             )
            return result

    @cached_property
    def user(self):
        # TODO: Adding the name to elastic and updating elastic when the user changes it's name is better than doing separate db lookups thousands of times per day.
        if not self.uploader_id:
            return None
        app.logger.warn('Additional database query for uploader')
        return models.User.by_id(self.elastic.uploader_id)

    @cached_property
    def sub_category(self):
        app.logger.warn('Additional database query for category')
        return models.SubCategory.by_category_ids(self.main_category_id, self.sub_category_id)

    @property
    def main_category(self):
        return self.sub_category.main_category

    @property
    def description(self):
        # Description isn't included in import_to_es (sync_es appears to have it), but only views for individual torrents use it, so it's not needed here
        app.logger.warn('description was accessed but is not available in elastic')
        return None

    @cached_property
    def magnet_uri(self):
        return torrents.create_magnet(self)


def create_elastic_client():
    es_hosts = app.config.get('ES_CLUSTER_HOSTS', ['localhost'])
    es_port = app.config.get('ES_CLUSTER_PORT', 9200)
    es_use_ssl = app.config.get('ES_CLUSTER_SSL', False)

    return Elasticsearch(hosts=es_hosts, port=es_port, use_ssl=es_use_ssl)


def get_elastic_sort(sort_by, sort_order):
    es_sort_keys = {
        'id': 'id',
        'size': 'filesize',
        # 'name': 'display_name',  # This is slow and buggy
        'seeders': 'seed_count',
        'leechers': 'leech_count',
        'downloads': 'download_count'
    }
    es_order_keys = {
        'desc': '-',
        'asc': ''
    }
    try:
        order_prefix = es_order_keys[sort_order.lower()]
    except KeyError:
        app.logger.warn('sort order {} unsupported'.format(sort_order))
        flask.abort(400)
    else:
        try:
            es_sort_key = es_sort_keys[sort_by.lower()]
        except KeyError:
            app.logger.warn('sort by {} unsupported'.format(sort_by))
            flask.abort(400)
        else:
            return order_prefix + es_sort_key


def get_elastic_category_filters(categories):
    category_filters = []
    for category in categories:
        main_cat = int(category / 100)
        sub_cat = int(category % 100)
        main_cat_filter = Q('term', main_category_id=main_cat)
        if not sub_cat:
            category_filters.append(main_cat_filter)
        else:
            sub_cat_filter = Q('term', sub_category_id=sub_cat)
            cat_filter = Q('bool', filter=[main_cat_filter, sub_cat_filter])
            category_filters.append(cat_filter)
    return category_filters


def get_elastic_tag_filters(include_tags, exclude_tags):
    supported_tags = ['remake', 'complete', 'anonymous']
    tag_filters = []
    for tag in include_tags:
        if not tag in supported_tags:
            app.logger.warn('include tag {} unsupported'.format(tag))
            flask.abort(400)
        query = {}
        query[tag] = True
        tag_filters.append(Q('term', **query))
    for tag in exclude_tags:
        if not tag in supported_tags:
            app.logger.warn('exclude tag {} unsupported'.format(tag))
            flask.abort(400)
        query = {}
        query[tag] = False
        tag_filters.append(Q('term', **query))
    return tag_filters

def search_elastic(term='', uploader_id=None,
                   categories=None, include_tags=[], exclude_tags=[],
                   sort_by='id', sort_order='desc', page=0, page_size=75,
                   logged_in_user_id=None, is_admin=False,
                   max_search_results=1000, include_total=False):
    es_client = create_elastic_client()

    query = Search(using=es_client, index=app.config.get('ES_INDEX_NAME'))

    if categories:
        category_filters = get_elastic_category_filters(categories)
        query = query.filter('bool', should=category_filters, minimum_should_match=1)

    if include_tags.count or exclude_tags.count:
        tag_filters = get_elastic_tag_filters(include_tags, exclude_tags)
        query = query.filter('bool', filter=tag_filters)

    if term:
        query = query.query('simple_query_string',
                            analyzer='my_search_analyzer',
                            default_operator="AND",
                            query=term)

    if not is_admin:
        # Hide all DELETED torrents if not admin
        query = query.filter('term', deleted=False)

    if uploader_id:
        # View only torrents uploaded by a specific user
        query = query.filter('term', uploader_id=uploader_id)
        if not is_admin:
            if not uploader_id == logged_in_user_id:
                # Hide all HIDDEN and ANONYMOUS torrents if the user isn't searching his own history
                query = query.filter('term', hidden=False)
                query = query.filter('term', anonymous=False)
    else:
        if not is_admin:
            if logged_in_user_id:
                # Hide all HIDDEN torrents unless it was uploaded the logged in user
                hiddenFilter = Q('term', hidden=False)
                userFilter = Q('term', uploader_id=logged_in_user_id)
                combinedFilter = hiddenFilter | userFilter
                query = query.filter('bool', filter=[combinedFilter])
            else:
                query = query.filter('term', hidden=False)

    # Apply sort
    es_sort = get_elastic_sort(sort_by, sort_order)
    query = query.sort(es_sort)

    highlight = app.config.get('ENABLE_ELASTIC_SEARCH_HIGHLIGHT')
    if highlight:
        query = query.highlight_options(tags_schema='styled')
        query = query.highlight("display_name")

    from_idx = min(max_search_results, (page - 1) * page_size)
    to_idx = min(max_search_results, from_idx + page_size)
    paged_query = query[from_idx:to_idx]

    paged_result = paged_query.execute()

    app.logger.debug('Elastic Query: {}'.format(json.dumps(paged_query.to_dict())))

    items = [ElasticItem(item) for item in paged_result]
    return Pagination(None, page, page_size, paged_result.hits.total, items)

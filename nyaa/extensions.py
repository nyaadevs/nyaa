import os.path

from flask import abort
from flask.config import Config
from flask_assets import Environment
from flask_debugtoolbar import DebugToolbarExtension
from flask_sqlalchemy import BaseQuery, Pagination, SQLAlchemy

assets = Environment()
db = SQLAlchemy()
toolbar = DebugToolbarExtension()


def fix_paginate():

    def paginate_faste(self, page=1, per_page=50, max_page=None, step=5, count_query=None):
        if page < 1:
            abort(404)

        if max_page and page > max_page:
            abort(404)

        # Count all items
        if count_query is not None:
            total_query_count = count_query.scalar()
        else:
            total_query_count = self.count()

        # Grab items on current page
        items = self.limit(per_page).offset((page - 1) * per_page).all()

        if not items and page != 1:
            abort(404)

        return Pagination(self, page, per_page, total_query_count, items)

    BaseQuery.paginate_faste = paginate_faste


def _get_config():
    # Workaround to get an available config object before the app is initiallized
    # Only needed/used in top-level and class statements
    # https://stackoverflow.com/a/18138250/7597273
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config = Config(root_path)
    config.from_object('config')
    return config


config = _get_config()

import logging
import os
import string

import flask
from flask_assets import Bundle  # noqa F401

from nyaa.api_handler import api_blueprint
from nyaa.extensions import assets, cache, db, fix_paginate, limiter, toolbar
from nyaa.template_utils import bp as template_utils_bp
from nyaa.template_utils import caching_url_for
from nyaa.utils import random_string
from nyaa.views import register_views

# Replace the Flask url_for with our cached version, since there's no real harm in doing so
# (caching_url_for has stored a reference to the OG url_for, so we won't recurse)
# Touching globals like this is a bit dirty, but nicer than replacing every url_for usage
flask.url_for = caching_url_for


def create_app(config):
    """ Nyaa app factory """
    app = flask.Flask(__name__)
    app.config.from_object(config)

    # Don't refresh cookie each request
    app.config['SESSION_REFRESH_EACH_REQUEST'] = False

    # Debugging
    if app.config['DEBUG']:
        app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
        toolbar.init_app(app)
        app.logger.setLevel(logging.DEBUG)

        # Forbid caching
        @app.after_request
        def forbid_cache(request):
            request.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            request.headers['Pragma'] = 'no-cache'
            request.headers['Expires'] = '0'
            return request

        # Add a timer header to the requests when debugging
        # This gives us a simple way to benchmark requests off-app
        import time

        @app.before_request
        def timer_before_request():
            flask.g.request_start_time = time.time()

        @app.after_request
        def timer_after_request(request):
            request.headers['X-Timer'] = time.time() - flask.g.request_start_time
            return request

    else:
        app.logger.setLevel(logging.WARNING)

    # Logging
    if 'LOG_FILE' in app.config:
        from logging.handlers import RotatingFileHandler
        app.log_handler = RotatingFileHandler(
            app.config['LOG_FILE'], maxBytes=10000, backupCount=1)
        app.logger.addHandler(app.log_handler)

    # Log errors and display a message to the user in production mdode
    if not app.config['DEBUG']:
        @app.errorhandler(500)
        def internal_error(exception):
            random_id = random_string(8, string.ascii_uppercase + string.digits)
            # Pst. Not actually unique, but don't tell anyone!
            app.logger.error('Exception occurred! Unique ID: %s', random_id, exc_info=exception)
            markup_source = ' '.join([
                '<strong>An error occurred!</strong>',
                'Debug information has been logged.',
                'Please pass along this ID: <kbd>{}</kbd>'.format(random_id)
            ])

            flask.flash(flask.Markup(markup_source), 'danger')
            return flask.redirect(flask.url_for('main.home'))

    # Get git commit hash
    app.config['COMMIT_HASH'] = None
    master_head = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               '../.git/refs/heads/master'))
    if os.path.isfile(master_head):
        with open(master_head, 'r') as head:
            app.config['COMMIT_HASH'] = head.readline().strip()

    # Enable the jinja2 do extension.
    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True

    # The default jinja_env has the OG Flask url_for (from before we replaced it),
    # so update the globals with our version
    app.jinja_env.globals['url_for'] = flask.url_for

    # Database
    fix_paginate()  # This has to be before the database is initialized
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MYSQL_DATABASE_CHARSET'] = 'utf8mb4'
    db.init_app(app)

    # Assets
    assets.init_app(app)
    assets._named_bundles = {}  # Hack to fix state carrying over in tests
    main_js = Bundle('js/main.js', filters='rjsmin', output='js/main.min.js')
    bs_js = Bundle('js/bootstrap-select.js', filters='rjsmin',
                   output='js/bootstrap-select.min.js')
    assets.register('main_js', main_js)
    assets.register('bs_js', bs_js)
    # css = Bundle('style.scss', filters='libsass',
    #             output='style.css', depends='**/*.scss')
    # assets.register('style_all', css)

    # Blueprints
    app.register_blueprint(template_utils_bp)
    app.register_blueprint(api_blueprint)
    register_views(app)

    # Pregenerate some URLs to avoid repeat url_for calls
    if 'SERVER_NAME' in app.config and app.config['SERVER_NAME']:
        with app.app_context():
            url = flask.url_for('static', filename='img/avatar/default.png', _external=True)
            app.config['DEFAULT_GRAVATAR_URL'] = url

    # Cache
    cache.init_app(app, config=app.config)

    # Rate Limiting, reads app.config itself
    limiter.init_app(app)

    return app

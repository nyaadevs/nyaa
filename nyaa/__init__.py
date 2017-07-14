import logging
import os

import flask
from flask_assets import Bundle  # noqa F401

from nyaa.extensions import assets, db, fix_paginate, toolbar

app = flask.Flask(__name__)
app.config.from_object('config')

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
        app.logger.error(exception)
        flask.flash(flask.Markup(
            '<strong>An error occurred!</strong> Debug information has been logged.'), 'danger')
        return flask.redirect('/')

# Get git commit hash
app.config['COMMIT_HASH'] = None
master_head = os.path.abspath(os.path.join(os.path.dirname(__file__), '../.git/refs/heads/master'))
if os.path.isfile(master_head):
    with open(master_head, 'r') as head:
        app.config['COMMIT_HASH'] = head.readline().strip()

# Enable the jinja2 do extension.
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True

# Database
fix_paginate()  # This has to be before the database is initialized
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MYSQL_DATABASE_CHARSET'] = 'utf8mb4'
db.init_app(app)

assets.init_app(app)

# css = Bundle('style.scss', filters='libsass',
#             output='style.css', depends='**/*.scss')
# assets.register('style_all', css)

with app.app_context():  # Temporary
    from nyaa import routes  # noqa E402 isort:skip

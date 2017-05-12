import os
import logging
import flask
from flask_sqlalchemy import SQLAlchemy
from flask_assets import Environment, Bundle
from flask_debugtoolbar import DebugToolbarExtension
from nyaa import fix_paginate


app = flask.Flask(__name__)
app.config.from_object('config')

# Database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Debugging
if app.config['DEBUG']:
    app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
    toolbar = DebugToolbarExtension(app)
    app.logger.setLevel(logging.DEBUG)
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
            '<strong>An error occured!</strong> Debugging information has been logged.'), 'danger')
        return flask.redirect('/')

# Enable the jinja2 do extension.
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True

db = SQLAlchemy(app)

assets = Environment(app)

# css = Bundle('style.scss', filters='libsass',
#             output='style.css', depends='**/*.scss')
# assets.register('style_all', css)

from nyaa import routes

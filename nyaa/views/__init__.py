import flask

from nyaa.views import (  # isort:skip
    account,
    admin,
    main,
    site,
    torrents,
    users,
)


def _maintenance_mode_hook():
    ''' Blocks POSTs, unless MAINTENANCE_MODE_LOGINS is True and the POST is for a login. '''
    if flask.request.method == 'POST':
        allow_logins = flask.current_app.config['MAINTENANCE_MODE_LOGINS']
        endpoint = flask.request.endpoint

        if not (allow_logins and endpoint == 'account.login'):
            message = 'Site is currently in maintenance mode.'

            # In case of an API request, return a plaintext error message
            if endpoint.startswith('api.'):
                resp = flask.make_response(message, 405)
                resp.headers['Content-Type'] = 'text/plain'
                return resp
            else:
                # Otherwise redirect to the target page and flash a message
                flask.flash(flask.Markup(message), 'danger')
                try:
                    target_url = flask.url_for(endpoint)
                except Exception:
                    # Non-GET-able endpoint, try referrer or default to home page
                    target_url = flask.request.referrer or flask.url_for('main.home')
                return flask.redirect(target_url)


def register_views(flask_app):
    """ Register the blueprints using the flask_app object """
    # Add our POST blocker first
    if flask_app.config['MAINTENANCE_MODE']:
        flask_app.before_request(_maintenance_mode_hook)

    flask_app.register_blueprint(account.bp)
    flask_app.register_blueprint(admin.bp)
    flask_app.register_blueprint(main.bp)
    flask_app.register_blueprint(site.bp)
    flask_app.register_blueprint(torrents.bp)
    flask_app.register_blueprint(users.bp)

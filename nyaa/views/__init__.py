from nyaa.views import (  # isort:skip
    account,
    admin,
    main,
    site,
    torrents,
    users,
)


def register_views(flask_app):
    """ Register the blueprints using the flask_app object """
    flask_app.register_blueprint(account.bp)
    flask_app.register_blueprint(admin.bp)
    flask_app.register_blueprint(main.bp)
    flask_app.register_blueprint(site.bp)
    flask_app.register_blueprint(torrents.bp)
    flask_app.register_blueprint(users.bp)

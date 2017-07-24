from nyaa import api_handler, app, template_utils, views
from nyaa.backend import get_category_id_map

DEBUG_API = False


@app.template_global()
def category_name(cat_id):
    ''' Given a category id (eg. 1_2), returns a category name (eg. Anime - English-translated) '''
    return ' - '.join(get_category_id_map().get(cat_id, ['???']))


# #################################### BLUEPRINTS ####################################

def register_blueprints(flask_app):
    """ Register the blueprints using the flask_app object """

    # Template filters and globals
    flask_app.register_blueprint(template_utils.bp)
    # API routes
    flask_app.register_blueprint(api_handler.api_blueprint, url_prefix='/api')
    # Site routes
    flask_app.register_blueprint(views.account_bp)
    flask_app.register_blueprint(views.admin_bp)
    flask_app.register_blueprint(views.main_bp)
    flask_app.register_blueprint(views.site_bp)
    flask_app.register_blueprint(views.torrents_bp)
    flask_app.register_blueprint(views.users_bp)


# When done, this can be moved to nyaa/__init__.py instead of importing this file
register_blueprints(app)

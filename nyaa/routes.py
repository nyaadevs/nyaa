from flask import current_app as app

from nyaa import template_utils, views
from nyaa.api_handler import api_blueprint

# Register all template filters and template globals
app.register_blueprint(template_utils.bp)
# Register the API routes
app.register_blueprint(api_blueprint, url_prefix='/api')
# Register the site's routes
views.register(app)

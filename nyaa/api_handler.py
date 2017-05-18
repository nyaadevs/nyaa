import flask
from werkzeug.datastructures import ImmutableMultiDict, CombinedMultiDict

from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, backend, utils
from nyaa import torrents

import functools
import json
import os.path
#from orderedset import OrderedSet
#from werkzeug import secure_filename

api_blueprint = flask.Blueprint('api', __name__)

# #################################### API HELPERS ####################################
def basic_auth_user(f):
    ''' A decorator that will try to validate the user into g.user from basic auth.
        Note: this does not set user to None on failure, so users can also authorize
        themselves with the cookie (handled in routes.before_request). '''
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        auth = flask.request.authorization
        if auth:
            user = models.User.by_username_or_email(auth.get('username'))
            if user and user.validate_authorization(auth.get('password')):
                flask.g.user = user

        return f(*args, **kwargs)
    return decorator

def api_require_user(f):
    ''' Returns an error message if flask.g.user is None.
        Remember to put after basic_auth_user. '''
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        if flask.g.user is None:
            return flask.jsonify({'errors':['Bad authorization']}), 403
        return f(*args, **kwargs)
    return decorator

def validate_user(upload_request):
    auth_info = None
    try:
        if 'auth_info' in upload_request.files:
            auth_info = json.loads(upload_request.files['auth_info'].read().decode('utf-8'))
            if 'username' not in auth_info.keys() or 'password' not in auth_info.keys():
                return False, None, None

            username = auth_info['username']
            password = auth_info['password']
            user = models.User.by_username(username)

            if not user:
                user = models.User.by_email(username)

            if (not user or password != user.password_hash or user.status == models.UserStatusType.INACTIVE):
                return False, None, None

            return True, user, None

    except Exception as e:
        return False, None, e


def _create_upload_category_choices():
    ''' Turns categories in the database into a list of (id, name)s '''
    choices = [('', '[Select a category]')]
    for main_cat in models.MainCategory.query.order_by(models.MainCategory.id):
        choices.append((main_cat.id_as_string, main_cat.name, True))
        for sub_cat in main_cat.sub_categories:
            choices.append((sub_cat.id_as_string, ' - ' + sub_cat.name))
    return choices


# #################################### API ROUTES ####################################
def api_upload(upload_request, user):
    form_info = None
    try:
        form_info = json.loads(upload_request.files['torrent_info'].read().decode('utf-8'))

        form_info_as_dict = []
        for k, v in form_info.items():
            if k in ['is_anonymous', 'is_hidden', 'is_remake', 'is_complete']:
                if v == True:
                    form_info_as_dict.append((k, v))
            else:
                form_info_as_dict.append((k, v))
        form_info = ImmutableMultiDict(form_info_as_dict)

        # print(repr(form_info))
    except Exception as e:
        return flask.make_response(flask.jsonify({'Failure': ['Invalid data. See HELP in api_uploader.py']}), 400)

    try:
        torrent_file = upload_request.files['torrent_file']
        torrent_file = ImmutableMultiDict([('torrent_file', torrent_file)])

        # print(repr(torrent_file))
    except Exception as e:
        pass

    form = forms.UploadForm(CombinedMultiDict((torrent_file, form_info)))
    form.category.choices = _create_upload_category_choices()

    if upload_request.method == 'POST' and form.validate():
        torrent = backend.handle_torrent_upload(form, user, True)

        return flask.make_response(flask.jsonify({'Success': int('{0}'.format(torrent.id))}), 200)
    else:
        # print(form.errors)
        return_error_messages = []
        for error_name, error_messages in form.errors.items():
            # print(error_messages)
            return_error_messages.extend(error_messages)

        return flask.make_response(flask.jsonify({'Failure': return_error_messages}), 400)

# V2 below

# Map UploadForm fields to API keys
UPLOAD_API_FORM_KEYMAP = {
    'torrent_file' : 'torrent',

    'display_name' : 'name',

    'is_anonymous' : 'anonymous',
    'is_hidden'    : 'hidden',
    'is_complete'  : 'complete',
    'is_remake'    : 'remake'
}
UPLOAD_API_FORM_KEYMAP_REVERSE = {v:k for k,v in UPLOAD_API_FORM_KEYMAP.items()}
UPLOAD_API_KEYS = [
    'name',
    'category',
    'anonymous',
    'hidden',
    'complete',
    'remake',
    'information',
    'description'
]

@api_blueprint.route('/v2/upload', methods=['POST'])
@basic_auth_user
@api_require_user
def v2_api_upload():
    mapped_dict = {
        'torrent_file' : flask.request.files.get('torrent')
    }

    request_data_field = flask.request.form.get('torrent_data')
    if request_data_field is None:
        return flask.jsonify({'errors' : ['missing torrent_data field']}), 400
    request_data = json.loads(request_data_field)

    # Map api keys to upload form fields
    for key in UPLOAD_API_KEYS:
        mapped_key = UPLOAD_API_FORM_KEYMAP_REVERSE.get(key, key)
        mapped_dict[mapped_key] = request_data.get(key)

    # Flask-WTF (very helpfully!!) automatically grabs the request form, so force a None formdata
    upload_form = forms.UploadForm(None, data=mapped_dict)
    upload_form.category.choices = _create_upload_category_choices()

    if upload_form.validate():
        torrent = backend.handle_torrent_upload(upload_form, flask.g.user)

        # Create a response dict with relevant data
        torrent_metadata = {
            'url' : flask.url_for('view_torrent', torrent_id=torrent.id, _external=True),
            'id'  : torrent.id,
            'name'  : torrent.display_name,
            'hash'   : torrent.info_hash.hex(),
            'magnet' : torrent.magnet_uri
        }

        return flask.jsonify(torrent_metadata)
    else:
        # Map errors back from form fields into the api keys
        mapped_errors = { UPLOAD_API_FORM_KEYMAP.get(k, k) : v for k,v in upload_form.errors.items() }
        return flask.jsonify({'errors' : mapped_errors}), 400

import binascii
import functools
import json
import re

import flask

from nyaa import backend, forms, models
from nyaa.views.torrents import _create_upload_category_choices

api_blueprint = flask.Blueprint('api', __name__, url_prefix='/api')

# #################################### API HELPERS ####################################


def basic_auth_user(f):
    ''' A decorator that will try to validate the user into g.user from basic auth.
        Note: this does not set user to None on failure, so users can also authorize
        themselves with the cookie (handled in views.main.before_request). '''
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
            return flask.jsonify({'errors': ['Bad authorization']}), 403
        return f(*args, **kwargs)
    return decorator


# #################################### API ROUTES ####################################

# Map UploadForm fields to API keys
UPLOAD_API_FORM_KEYMAP = {
    'torrent_file': 'torrent',

    'display_name': 'name',

    'is_anonymous': 'anonymous',
    'is_hidden': 'hidden',
    'is_complete': 'complete',
    'is_remake': 'remake',
    'is_trusted': 'trusted'
}
UPLOAD_API_FORM_KEYMAP_REVERSE = {v: k for k, v in UPLOAD_API_FORM_KEYMAP.items()}
UPLOAD_API_DEFAULTS = {
    'name': '',
    'category': '',
    'anonymous': False,
    'hidden': False,
    'complete': False,
    'remake': False,
    'trusted': True,
    'information': '',
    'description': ''
}


@api_blueprint.route('/upload', methods=['POST'])
@api_blueprint.route('/v2/upload', methods=['POST'])
@basic_auth_user
@api_require_user
def v2_api_upload():
    mapped_dict = {
        'torrent_file': flask.request.files.get('torrent')
    }

    request_data_field = flask.request.form.get('torrent_data')
    if request_data_field is None:
        return flask.jsonify({'errors': ['missing torrent_data field']}), 400

    try:
        request_data = json.loads(request_data_field)
    except json.decoder.JSONDecodeError:
        return flask.jsonify({'errors': ['unable to parse valid JSON in torrent_data']}), 400

    # Map api keys to upload form fields
    for key, default in UPLOAD_API_DEFAULTS.items():
        mapped_key = UPLOAD_API_FORM_KEYMAP_REVERSE.get(key, key)
        value = request_data.get(key, default)
        mapped_dict[mapped_key] = value if value is not None else default

    # Flask-WTF (very helpfully!!) automatically grabs the request form, so force a None formdata
    upload_form = forms.UploadForm(None, data=mapped_dict, meta={'csrf': False})
    upload_form.category.choices = _create_upload_category_choices()

    if upload_form.validate():
        try:
            torrent = backend.handle_torrent_upload(upload_form, flask.g.user)

            # Create a response dict with relevant data
            torrent_metadata = {
                'url': flask.url_for('torrents.view', torrent_id=torrent.id, _external=True),
                'id': torrent.id,
                'name': torrent.display_name,
                'hash': torrent.info_hash.hex(),
                'magnet': torrent.magnet_uri
            }

            return flask.jsonify(torrent_metadata)
        except backend.TorrentExtraValidationException:
            pass

    # Map errors back from form fields into the api keys
    mapped_errors = {UPLOAD_API_FORM_KEYMAP.get(k, k): v for k, v in upload_form.errors.items()}
    return flask.jsonify({'errors': mapped_errors}), 400


# ####################################### INFO #######################################
ID_PATTERN = '^[0-9]+$'
INFO_HASH_PATTERN = '^[0-9a-fA-F]{40}$'  # INFO_HASH as string


@api_blueprint.route('/info/<torrent_id_or_hash>', methods=['GET'])
@basic_auth_user
@api_require_user
def v2_api_info(torrent_id_or_hash):
    torrent_id_or_hash = torrent_id_or_hash.lower().strip()

    id_match = re.match(ID_PATTERN, torrent_id_or_hash)
    hex_hash_match = re.match(INFO_HASH_PATTERN, torrent_id_or_hash)

    torrent = None

    if id_match:
        torrent = models.Torrent.by_id(int(torrent_id_or_hash))
    elif hex_hash_match:
        # Convert the string representation of a torrent hash back into a binary representation
        a2b_hash = binascii.unhexlify(torrent_id_or_hash)
        torrent = models.Torrent.by_info_hash(a2b_hash)
    else:
        return flask.jsonify({'errors': ['Query was not a valid id or hash.']}), 400

    viewer = flask.g.user

    if not torrent:
        return flask.jsonify({'errors': ['Query was not a valid id or hash.']}), 400

    # Only allow admins see deleted torrents
    if torrent.deleted and not (viewer and viewer.is_superadmin):
        return flask.jsonify({'errors': ['Query was not a valid id or hash.']}), 400

    submitter = None
    if not torrent.anonymous and torrent.user:
        submitter = torrent.user.username
    if torrent.user and (viewer == torrent.user or viewer.is_moderator):
        submitter = torrent.user.username

    files = {}
    if torrent.filelist:
        files = json.loads(torrent.filelist.filelist_blob.decode('utf-8'))

    # Create a response dict with relevant data
    torrent_metadata = {
        'submitter': submitter,
        'url': flask.url_for('torrents.view', torrent_id=torrent.id, _external=True),
        'id': torrent.id,
        'name': torrent.display_name,

        'creation_date': torrent.created_time.strftime('%Y-%m-%d %H:%M UTC'),
        'hash_b32': torrent.info_hash_as_b32,  # as used in magnet uri
        'hash_hex': torrent.info_hash_as_hex,  # .hex(), #as shown in torrent client
        'magnet': torrent.magnet_uri,

        'main_category': torrent.main_category.name,
        'main_category_id': torrent.main_category.id,
        'sub_category': torrent.sub_category.name,
        'sub_category_id': torrent.sub_category.id,

        'information': torrent.information,
        'description': torrent.description,
        'stats': {
            'seeders': torrent.stats.seed_count,
            'leechers': torrent.stats.leech_count,
            'downloads': torrent.stats.download_count
        },
        'filesize': torrent.filesize,
        'files': files,

        'is_trusted': torrent.trusted,
        'is_complete': torrent.complete,
        'is_remake': torrent.remake
    }

    return flask.jsonify(torrent_metadata), 200

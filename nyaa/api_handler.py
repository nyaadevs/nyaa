import flask
from werkzeug.datastructures import ImmutableMultiDict, CombinedMultiDict

from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, backend, utils
from nyaa import torrents

# For _create_upload_category_choices
from nyaa import routes

import functools
import json
import os.path

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
    request_data = json.loads(request_data_field)

    # Map api keys to upload form fields
    for key, default in UPLOAD_API_DEFAULTS.items():
        mapped_key = UPLOAD_API_FORM_KEYMAP_REVERSE.get(key, key)
        mapped_dict[mapped_key] = request_data.get(key, default)

    # Flask-WTF (very helpfully!!) automatically grabs the request form, so force a None formdata
    upload_form = forms.UploadForm(None, data=mapped_dict, meta={'csrf': False})
    upload_form.category.choices = routes._create_upload_category_choices()

    if upload_form.validate():
        torrent = backend.handle_torrent_upload(upload_form, flask.g.user)

        # Create a response dict with relevant data
        torrent_metadata = {
            'url': flask.url_for('view_torrent', torrent_id=torrent.id, _external=True),
            'id': torrent.id,
            'name': torrent.display_name,
            'hash': torrent.info_hash.hex(),
            'magnet': torrent.magnet_uri
        }

        return flask.jsonify(torrent_metadata)
    else:
        # Map errors back from form fields into the api keys
        mapped_errors = {UPLOAD_API_FORM_KEYMAP.get(k, k): v for k, v in upload_form.errors.items()}
        return flask.jsonify({'errors': mapped_errors}), 400


# #################################### TEMPORARY ####################################

from orderedset import OrderedSet  # noqa: E402


@api_blueprint.route('/ghetto_import', methods=['POST'])
def ghetto_import():
    if flask.request.remote_addr != '127.0.0.1':
        return flask.error(403)

    torrent_file = flask.request.files.get('torrent')

    try:
        torrent_dict = bencode.decode(torrent_file)
        # field.data.close()
    except (bencode.MalformedBencodeException, UnicodeError):
        return 'Malformed torrent file', 500

    try:
        forms._validate_torrent_metadata(torrent_dict)
    except AssertionError as e:
        return 'Malformed torrent metadata ({})'.format(e.args[0]), 500

    try:
        tracker_found = forms._validate_trackers(torrent_dict)
    except AssertionError as e:
        return 'Malformed torrent trackers ({})'.format(e.args[0]), 500

    bencoded_info_dict = bencode.encode(torrent_dict['info'])
    info_hash = utils.sha1_hash(bencoded_info_dict)

    # Check if the info_hash exists already in the database
    torrent = models.Torrent.by_info_hash(info_hash)
    if not torrent:
        return 'This torrent does not exists', 500

    if torrent.has_torrent:
        return 'This torrent already has_torrent', 500

    # Torrent is legit, pass original filename and dict along
    torrent_data = forms.TorrentFileData(filename=os.path.basename(torrent_file.filename),
                                         torrent_dict=torrent_dict,
                                         info_hash=info_hash,
                                         bencoded_info_dict=bencoded_info_dict)

    # The torrent has been  validated and is safe to access with ['foo'] etc - all relevant
    # keys and values have been checked for (see UploadForm in forms.py for details)
    info_dict = torrent_data.torrent_dict['info']

    changed_to_utf8 = backend._replace_utf8_values(torrent_data.torrent_dict)

    torrent_filesize = info_dict.get('length') or sum(
        f['length'] for f in info_dict.get('files'))

    # In case no encoding, assume UTF-8.
    torrent_encoding = torrent_data.torrent_dict.get('encoding', b'utf-8').decode('utf-8')

    # Store bencoded info_dict
    torrent.info = models.TorrentInfo(info_dict=torrent_data.bencoded_info_dict)
    torrent.has_torrent = True

    # To simplify parsing the filelist, turn single-file torrent into a list
    torrent_filelist = info_dict.get('files')

    used_path_encoding = changed_to_utf8 and 'utf-8' or torrent_encoding

    parsed_file_tree = dict()
    if not torrent_filelist:
        # If single-file, the root will be the file-tree (no directory)
        file_tree_root = parsed_file_tree
        torrent_filelist = [{'length': torrent_filesize, 'path': [info_dict['name']]}]
    else:
        # If multi-file, use the directory name as root for files
        file_tree_root = parsed_file_tree.setdefault(
            info_dict['name'].decode(used_path_encoding), {})

    # Parse file dicts into a tree
    for file_dict in torrent_filelist:
        # Decode path parts from utf8-bytes
        path_parts = [path_part.decode(used_path_encoding) for path_part in file_dict['path']]

        filename = path_parts.pop()
        current_directory = file_tree_root

        for directory in path_parts:
            current_directory = current_directory.setdefault(directory, {})

        # Don't add empty filenames (BitComet directory)
        if filename:
            current_directory[filename] = file_dict['length']

    parsed_file_tree = utils.sorted_pathdict(parsed_file_tree)

    json_bytes = json.dumps(parsed_file_tree, separators=(',', ':')).encode('utf8')
    torrent.filelist = models.TorrentFilelist(filelist_blob=json_bytes)

    db.session.add(torrent)
    db.session.flush()

    # Store the users trackers
    trackers = OrderedSet()
    announce = torrent_data.torrent_dict.get('announce', b'').decode('ascii')
    if announce:
        trackers.add(announce)

    # List of lists with single item
    announce_list = torrent_data.torrent_dict.get('announce-list', [])
    for announce in announce_list:
        trackers.add(announce[0].decode('ascii'))

    # Remove our trackers, maybe? TODO ?

    # Search for/Add trackers in DB
    db_trackers = OrderedSet()
    for announce in trackers:
        tracker = models.Trackers.by_uri(announce)

        # Insert new tracker if not found
        if not tracker:
            tracker = models.Trackers(uri=announce)
            db.session.add(tracker)

        db_trackers.add(tracker)

    db.session.flush()

    # Store tracker refs in DB
    for order, tracker in enumerate(db_trackers):
        torrent_tracker = models.TorrentTrackers(torrent_id=torrent.id,
                                                 tracker_id=tracker.id, order=order)
        db.session.add(torrent_tracker)

    db.session.commit()

    return 'success'

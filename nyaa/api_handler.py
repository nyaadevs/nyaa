import flask
from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, utils
from nyaa import torrents

import json
import os.path
from orderedset import OrderedSet
from werkzeug import secure_filename

DEBUG_API = False
# #################################### API ROUTES ####################################
CATEGORIES = [
    ('Anime', ['Anime Music Video', 'English-translated', 'Non-English-translated', 'Raw']),
    ('Audio', ['Lossless', 'Lossy']),
    ('Literature', ['English-translated', 'Non-English-translated', 'Raw']),
    ('Live Action', ['English-translated',
                     'Idol/Promotional Video', 'Non-English-translated', 'Raw']),
    ('Pictures', ['Graphics', 'Photos']),
    ('Software', ['Applications', 'Games']),
]


def validate_main_sub_cat(main_cat_name, sub_cat_name):
    for main_cat in models.MainCategory.query.order_by(models.MainCategory.id):
        if main_cat_name == main_cat.name:
            for sub_cat in main_cat.sub_categories:
                if sub_cat_name == sub_cat.name:
                    cat_id = main_cat.id_as_string
                    sub_cat_id = sub_cat.id_as_string
                    cat_sub_cat = sub_cat_id.split('_')
                    # print('cat: {0} sub_cat: {1}'.format(cat_sub_cat[0], cat_sub_cat[1]))

                    return True, cat_sub_cat[0], cat_sub_cat[1]

        return False, 0, 0


def _replace_utf8_values(dict_or_list):
    ''' Will replace 'property' with 'property.utf-8' and remove latter if it exists.
        Thanks, bitcomet! :/ '''
    did_change = False
    if isinstance(dict_or_list, dict):
        for key in [key for key in dict_or_list.keys() if key.endswith('.utf-8')]:
            dict_or_list[key.replace('.utf-8', '')] = dict_or_list.pop(key)
            did_change = True
        for value in dict_or_list.values():
            did_change = _replace_utf8_values(value) or did_change
    elif isinstance(dict_or_list, list):
        for item in dict_or_list:
            did_change = _replace_utf8_values(item) or did_change
    return did_change


def validate_torrent_flags(torrent_flags):
    _torrent_flags = ['hidden', 'remake', 'complete', 'anonymous']

    if len(torrent_flags) != 4:
        return False

    for flag in torrent_flags:
        if int(flag) not in [0, 1]:
            return False
    return True

# It might be good to factor this out of forms UploadForm because the same code is
# used in both files.


def validate_torrent_file(torrent_file_name, torrent_file):
    # Decode and ensure data is bencoded data
    try:
        torrent_dict = bencode.decode(torrent_file)
    except (bencode.MalformedBencodeException, UnicodeError):
        return False, 'Malformed torrent file'

    # Uncomment for debug print of the torrent
    # forms._debug_print_torrent_metadata(torrent_dict)

    try:
        forms._validate_torrent_metadata(torrent_dict)
    except AssertionError as e:
        return False, 'Malformed torrent metadata ({})'.format(e.args[0])

    # Note! bencode will sort dict keys, as per the spec
    # This may result in a different hash if the uploaded torrent does not match the
    # spec, but it's their own fault for using broken software! Right?
    bencoded_info_dict = bencode.encode(torrent_dict['info'])
    info_hash = utils.sha1_hash(bencoded_info_dict)

    # Check if the info_hash exists already in the database
    existing_torrent = models.Torrent.by_info_hash(info_hash)
    if existing_torrent:
        return False, 'That torrent already exists (#{})'.format(existing_torrent.id)

    # Torrent is legit, pass original filename and dict along
    return True, forms.TorrentFileData(filename=os.path.basename(torrent_file_name),
                                       torrent_dict=torrent_dict,
                                       info_hash=info_hash,
                                       bencoded_info_dict=bencoded_info_dict)


def api_upload(upload_request):
    if upload_request.method == 'POST':
        j = None
        torrent_file = None
        try:
            if 'json' in upload_request.files:
                f = upload_request.files['json']
                j = json.loads(f.read().decode('utf-8'))
                if DEBUG_API:
                    print(json.dumps(j, indent=4))

                _json_keys = ['username', 'password',
                              'display_name', 'main_cat', 'sub_cat', 'flags']  # 'information' and 'description' are not required
                # Check that required fields are present
                for _k in _json_keys:
                    if _k not in j.keys():
                        return flask.make_response(flask.jsonify({"Error": "Missing JSON field: {0}.".format(_k)}), 400)
                # Check that no extra fields are present
                for k in j.keys():
                    if k not in ['username', 'password',
                                 'display_name', 'main_cat', 'sub_cat', 'information', 'description', 'flags']:
                        return flask.make_response(flask.jsonify({"Error": "Incorrect JSON field(s)."}), 400)
            else:
                return flask.make_response(flask.jsonify({"Error": "No metadata."}), 400)
            if 'torrent' in upload_request.files:
                f = upload_request.files['torrent']
                if DEBUG_API:
                    print(f.filename)
                torrent_file = f
                # print(f.read())
            else:
                return flask.make_response(flask.jsonify({"Error": "No torrent file."}), 400)

            # 'username' and 'password' must have been provided as they are part of j.keys()
            username = j['username']
            password = j['password']
            # Validate that the provided username and password belong to a valid user
            user = models.User.by_username(username)

            if not user:
                user = models.User.by_email(username)

            if not user or password != user.password_hash or user.status == models.UserStatusType.INACTIVE:
                return flask.make_response(flask.jsonify({"Error": "Incorrect username or password"}), 403)

            current_user = user

            display_name = j['display_name']
            if (len(display_name) < 3) or (len(display_name) > 1024):
                return flask.make_response(flask.jsonify({"Error": "Torrent name must be between 3 and 1024 characters."}), 400)

            main_cat_name = j['main_cat']
            sub_cat_name = j['sub_cat']

            cat_subcat_status, cat_id, sub_cat_id = validate_main_sub_cat(
                main_cat_name, sub_cat_name)
            if not cat_subcat_status:
                return flask.make_response(flask.jsonify({"Error": "Incorrect Category / Sub-Category."}), 400)

            # TODO Sanitize information
            information = None
            try:
                information = j['information']
                if len(information) > 255:
                    return flask.make_response(flask.jsonify({"Error": "Information is limited to 255 characters."}), 400)
            except Exception as e:
                information = ''

            # TODO Sanitize description
            description = None
            try:
                description = j['description']
                if len(description) > (10 * 1024):
                    return flask.make_response(flask.jsonify({"Error": "Description is limited to {0} characters.".format(10 * 1024)}), 403)
            except Exception as e:
                description = ''

            v_flags = validate_torrent_flags(j['flags'])
            if v_flags:
                torrent_flags = j['flags']
            else:
                return flask.make_response(flask.jsonify({"Error": "Incorrect torrent flags."}), 400)

            torrent_status, torrent_data = validate_torrent_file(
                torrent_file.filename, torrent_file.read())  # Needs validation

            if not torrent_status:
                return flask.make_response(flask.jsonify({"Error": "Invalid or Duplicate torrent file."}), 400)

            # The torrent has been  validated and is safe to access with ['foo'] etc - all relevant
            # keys and values have been checked for (see UploadForm in forms.py for details)
            info_dict = torrent_data.torrent_dict['info']

            changed_to_utf8 = _replace_utf8_values(torrent_data.torrent_dict)

            torrent_filesize = info_dict.get('length') or sum(
                f['length'] for f in info_dict.get('files'))

            # In case no encoding, assume UTF-8.
            torrent_encoding = torrent_data.torrent_dict.get('encoding', b'utf-8').decode('utf-8')

            torrent = models.Torrent(info_hash=torrent_data.info_hash,
                                     display_name=display_name,
                                     torrent_name=torrent_data.filename,
                                     information=information,
                                     description=description,
                                     encoding=torrent_encoding,
                                     filesize=torrent_filesize,
                                     user=current_user)

            # Store bencoded info_dict
            torrent.info = models.TorrentInfo(info_dict=torrent_data.bencoded_info_dict)
            torrent.stats = models.Statistic()
            torrent.has_torrent = True

            # Fields with default value will be None before first commit, so set .flags
            torrent.flags = 0

            torrent.anonymous = True if torrent_flags[0] else False
            torrent.hidden = True if torrent_flags[1] else False
            torrent.remake = True if torrent_flags[2] else False
            torrent.complete = True if torrent_flags[3] else False
            # Copy trusted status from user if possible
            torrent.trusted = (current_user.level >=
                               models.UserLevelType.TRUSTED) if current_user else False

            # Set category ids
            torrent.main_category_id = cat_id
            torrent.sub_category_id = sub_cat_id
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
                path_parts = [path_part.decode(used_path_encoding)
                              for path_part in file_dict['path']]

                filename = path_parts.pop()
                current_directory = file_tree_root

                for directory in path_parts:
                    current_directory = current_directory.setdefault(directory, {})

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

            if app.config.get('BACKUP_TORRENT_FOLDER'):
                torrent_file.seek(0, 0)
                torrent_path = os.path.join(app.config['BACKUP_TORRENT_FOLDER'], '{}.{}'.format(
                    torrent.id, secure_filename(torrent_file.filename)))
                torrent_file.save(torrent_path)
            torrent_file.close()

            # print('Success? {0}'.format(torrent.id))
            return flask.make_response(flask.jsonify({"Success": "Request was processed {0}".format(torrent.id)}), 200)
        except Exception as e:
            print('Exception: {0}'.format(e))
            return flask.make_response(flask.jsonify({"Error": "Incorrect JSON. Please see HELP page for examples."}), 400)
    else:
        return flask.make_response(flask.jsonify({"Error": "Bad request"}), 400)

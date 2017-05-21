import flask
from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, utils

import os

import json
from werkzeug import secure_filename
from collections import OrderedDict
from orderedset import OrderedSet
from ipaddress import ip_address


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


def handle_torrent_upload(upload_form, uploading_user=None, fromAPI=False):
    torrent_data = upload_form.torrent_file.parsed_data

    # The torrent has been  validated and is safe to access with ['foo'] etc - all relevant
    # keys and values have been checked for (see UploadForm in forms.py for details)
    info_dict = torrent_data.torrent_dict['info']

    changed_to_utf8 = _replace_utf8_values(torrent_data.torrent_dict)

    # Use uploader-given name or grab it from the torrent
    display_name = upload_form.display_name.data.strip() or info_dict['name'].decode('utf8').strip()
    information = (upload_form.information.data or '').strip()
    description = (upload_form.description.data or '').strip()

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
                             user=uploading_user,
                             uploader_ip=ip_address(flask.request.remote_addr).packed)

    # Store bencoded info_dict
    torrent.info = models.TorrentInfo(info_dict=torrent_data.bencoded_info_dict)
    torrent.stats = models.Statistic()
    torrent.has_torrent = True

    # Fields with default value will be None before first commit, so set .flags
    torrent.flags = 0

    torrent.anonymous = upload_form.is_anonymous.data if uploading_user else True
    torrent.hidden = upload_form.is_hidden.data
    torrent.remake = upload_form.is_remake.data
    torrent.complete = upload_form.is_complete.data
    # Copy trusted status from user if possible
    can_mark_trusted = uploading_user and uploading_user.is_trusted
    torrent.trusted = upload_form.is_trusted.data if can_mark_trusted else False
    # Set category ids
    torrent.main_category_id, torrent.sub_category_id = \
        upload_form.category.parsed_data.get_category_ids()

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

    # Store the actual torrent file as well
    torrent_file = upload_form.torrent_file.data
    if app.config.get('BACKUP_TORRENT_FOLDER'):
        torrent_file.seek(0, 0)

        torrent_dir = app.config['BACKUP_TORRENT_FOLDER']
        if not os.path.exists(torrent_dir):
            os.makedirs(torrent_dir)

        torrent_path = os.path.join(torrent_dir, '{}.{}'.format(
            torrent.id, secure_filename(torrent_file.filename)))
        torrent_file.save(torrent_path)
    torrent_file.close()

    return torrent

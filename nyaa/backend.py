import json
import os
import re
from datetime import datetime, timedelta
from ipaddress import ip_address

import flask
from werkzeug import secure_filename

import sqlalchemy
from orderedset import OrderedSet

from nyaa import models, utils
from nyaa.extensions import db

app = flask.current_app

# Blacklists for _validate_torrent_filenames
# TODO: consider moving to config.py?
CHARACTER_BLACKLIST = [
    '\u202E',  # RIGHT-TO-LEFT OVERRIDE
]
FILENAME_BLACKLIST = [
    # Windows reserved filenames
    'con',
    'nul',
    'prn',
    'aux',
    'com0', 'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt0', 'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
]

# Invalid RSS characters regex, used to sanitize some strings
ILLEGAL_XML_CHARS_RE = re.compile(u'[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]')


def sanitize_string(string, replacement='\uFFFD'):
    ''' Simply replaces characters based on a regex '''
    return ILLEGAL_XML_CHARS_RE.sub(replacement, string)


class TorrentExtraValidationException(Exception):
    def __init__(self, errors={}):
        self.errors = errors


@utils.cached_function
def get_category_id_map():
    ''' Reads database for categories and turns them into a dict with
        ids as keys and name list as the value, ala
        {'1_0': ['Anime'], '1_2': ['Anime', 'English-translated'], ...} '''
    cat_id_map = {}
    for main_cat in models.MainCategory.query:
        cat_id_map[main_cat.id_as_string] = [main_cat.name]
        for sub_cat in main_cat.sub_categories:
            cat_id_map[sub_cat.id_as_string] = [main_cat.name, sub_cat.name]
    return cat_id_map


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


def _recursive_dict_iterator(source):
    ''' Iterates over a given dict, yielding (key, value) pairs,
        recursing inside any dicts. '''
    # TODO Make a proper dict-filetree walker
    for key, value in source.items():
        yield (key, value)

        if isinstance(value, dict):
            for kv in _recursive_dict_iterator(value):
                yield kv


def _validate_torrent_filenames(torrent):
    ''' Checks path parts of a torrent's filetree against blacklisted characters
        and filenames, returning False on rejection '''
    file_tree = json.loads(torrent.filelist.filelist_blob.decode('utf-8'))

    for path_part, value in _recursive_dict_iterator(file_tree):
        if path_part.rsplit('.', 1)[0].lower() in FILENAME_BLACKLIST:
            return False
        if any(True for c in CHARACTER_BLACKLIST if c in path_part):
            return False

    return True


def validate_torrent_post_upload(torrent, upload_form=None):
    ''' Validates a Torrent instance before it's saved to the database.
        Enforcing user-and-such-based validations is more flexible here vs WTForm context '''
    errors = {
        'torrent_file': []
    }

    # Encorce minimum size for userless uploads
    minimum_anonymous_torrent_size = app.config['MINIMUM_ANONYMOUS_TORRENT_SIZE']
    if torrent.user is None and torrent.filesize < minimum_anonymous_torrent_size:
        errors['torrent_file'].append('Torrent too small for an anonymous uploader')

    if not _validate_torrent_filenames(torrent):
        errors['torrent_file'].append('Torrent has forbidden characters in filenames')

    # Remove keys with empty lists
    errors = {k: v for k, v in errors.items() if v}
    if errors:
        if upload_form:
            # Add error messages to the form fields
            for field_name, field_errors in errors.items():
                getattr(upload_form, field_name).errors.extend(field_errors)
            # Clear out the wtforms dict to force a regeneration
            upload_form._errors = None

        raise TorrentExtraValidationException(errors)


def check_uploader_ratelimit(user):
    ''' Figures out if user (or IP address from flask.request) may
        upload within upload ratelimit.
        Returns a tuple of current datetime, count of torrents uploaded
        within burst duration and timestamp for next allowed upload. '''
    now = datetime.utcnow()
    next_allowed_time = now

    Torrent = models.Torrent

    def filter_uploader(query):
        if user:
            return query.filter(sqlalchemy.or_(
                Torrent.user == user,
                Torrent.uploader_ip == ip_address(flask.request.remote_addr).packed))
        else:
            return query.filter(Torrent.uploader_ip == ip_address(flask.request.remote_addr).packed)

    time_range_start = datetime.utcnow() - timedelta(seconds=app.config['UPLOAD_BURST_DURATION'])
    # Count torrents uploaded by user/ip within given time period
    torrent_count_query = db.session.query(sqlalchemy.func.count(Torrent.id))
    torrent_count = filter_uploader(torrent_count_query).filter(
        Torrent.created_time >= time_range_start).scalar()

    # If user has reached burst limit...
    if torrent_count >= app.config['MAX_UPLOAD_BURST']:
        # Check how long ago their latest torrent was (we know at least one will exist)
        last_torrent = filter_uploader(Torrent.query).order_by(Torrent.created_time.desc()).first()
        after_timeout = last_torrent.created_time + timedelta(seconds=app.config['UPLOAD_TIMEOUT'])

        if now < after_timeout:
            next_allowed_time = after_timeout

    return now, torrent_count, next_allowed_time


def handle_torrent_upload(upload_form, uploading_user=None, fromAPI=False):
    ''' Stores a torrent to the database.
        May throw TorrentExtraValidationException if the form/torrent fails
        post-WTForm validation! Exception messages will also be added to their
        relevant fields on the given form. '''
    torrent_data = upload_form.torrent_file.parsed_data

    # Anonymous uploaders and non-trusted uploaders
    no_or_new_account = (not uploading_user
                         or (uploading_user.age < app.config['RATELIMIT_ACCOUNT_AGE']
                             and not uploading_user.is_trusted))

    if app.config['RATELIMIT_UPLOADS'] and no_or_new_account:
        now, torrent_count, next_time = check_uploader_ratelimit(uploading_user)
        if next_time > now:
            # This will flag the dialog in upload.html red and tell API users what's wrong
            upload_form.ratelimit.errors = ["You've gone over the upload ratelimit."]
            raise TorrentExtraValidationException()

    if not uploading_user:
        if app.config['RAID_MODE_LIMIT_UPLOADS']:
            # XXX TODO: rename rangebanned to something more generic
            upload_form.rangebanned.errors = [app.config['RAID_MODE_UPLOADS_MESSAGE']]
            raise TorrentExtraValidationException()
        elif models.RangeBan.is_rangebanned(ip_address(flask.request.remote_addr).packed):
            upload_form.rangebanned.errors = ["Your IP is banned from "
                                              "uploading anonymously."]
            raise TorrentExtraValidationException()

    # Delete existing torrent which is marked as deleted
    if torrent_data.db_id is not None:
        old_torrent = models.Torrent.by_id(torrent_data.db_id)
        db.session.delete(old_torrent)
        db.session.commit()
        # Delete physical file after transaction has been committed
        _delete_info_dict(old_torrent)

    # The torrent has been  validated and is safe to access with ['foo'] etc - all relevant
    # keys and values have been checked for (see UploadForm in forms.py for details)
    info_dict = torrent_data.torrent_dict['info']

    changed_to_utf8 = _replace_utf8_values(torrent_data.torrent_dict)

    # Use uploader-given name or grab it from the torrent
    display_name = upload_form.display_name.data.strip() or info_dict['name'].decode('utf8').strip()
    information = (upload_form.information.data or '').strip()
    description = (upload_form.description.data or '').strip()

    # Sanitize fields
    display_name = sanitize_string(display_name)
    information = sanitize_string(information)
    description = sanitize_string(description)

    torrent_filesize = info_dict.get('length') or sum(
        f['length'] for f in info_dict.get('files'))

    # In case no encoding, assume UTF-8.
    torrent_encoding = torrent_data.torrent_dict.get('encoding', b'utf-8').decode('utf-8')

    torrent = models.Torrent(id=torrent_data.db_id,
                             info_hash=torrent_data.info_hash,
                             display_name=display_name,
                             torrent_name=torrent_data.filename,
                             information=information,
                             description=description,
                             encoding=torrent_encoding,
                             filesize=torrent_filesize,
                             user=uploading_user,
                             uploader_ip=ip_address(flask.request.remote_addr).packed)

    # Store bencoded info_dict
    info_dict_path = torrent.info_dict_path

    info_dict_dir = os.path.dirname(info_dict_path)
    os.makedirs(info_dict_dir, exist_ok=True)

    with open(info_dict_path, 'wb') as out_file:
        out_file.write(torrent_data.bencoded_info_dict)

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
    # To do, automatically mark trusted if user is trusted unless user specifies otherwise
    torrent.trusted = upload_form.is_trusted.data if can_mark_trusted else False

    # Only allow mods to upload locked torrents
    can_mark_locked = uploading_user and uploading_user.is_moderator
    torrent.comment_locked = upload_form.is_comment_locked.data if can_mark_locked else False

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

    # Store webseeds
    # qBittorrent doesn't omit url-list but sets it as '' even when there are no webseeds
    webseed_list = torrent_data.torrent_dict.get('url-list') or []
    if isinstance(webseed_list, bytes):
        webseed_list = [webseed_list]  # qB doesn't contain a sole url in a list
    webseeds = OrderedSet(webseed.decode('utf-8') for webseed in webseed_list)

    # Remove our trackers, maybe? TODO ?

    # Search for/Add trackers in DB
    db_trackers = OrderedSet()
    for announce in trackers:
        tracker = models.Trackers.by_uri(announce)

        # Insert new tracker if not found
        if not tracker:
            tracker = models.Trackers(uri=announce)
            db.session.add(tracker)
            db.session.flush()
        elif tracker.is_webseed:
            # If we have an announce marked webseed (user error, malicy?), reset it.
            # Better to have "bad" announces than "hiding" proper announces in webseeds/url-list.
            tracker.is_webseed = False
            db.session.flush()

        db_trackers.add(tracker)

    # Same for webseeds
    for webseed_url in webseeds:
        webseed = models.Trackers.by_uri(webseed_url)

        if not webseed:
            webseed = models.Trackers(uri=webseed_url, is_webseed=True)
            db.session.add(webseed)
            db.session.flush()

        # Don't add trackers into webseeds
        if webseed.is_webseed:
            db_trackers.add(webseed)

    # Store tracker refs in DB
    for order, tracker in enumerate(db_trackers):
        torrent_tracker = models.TorrentTrackers(torrent_id=torrent.id,
                                                 tracker_id=tracker.id, order=order)
        db.session.add(torrent_tracker)

    # Before final commit, validate the torrent again
    validate_torrent_post_upload(torrent, upload_form)

    # Add to tracker whitelist
    db.session.add(models.TrackerApi(torrent.info_hash, 'insert'))

    db.session.commit()

    # Store the actual torrent file as well
    torrent_file = upload_form.torrent_file.data
    if app.config.get('BACKUP_TORRENT_FOLDER'):
        torrent_file.seek(0, 0)

        torrent_dir = app.config['BACKUP_TORRENT_FOLDER']
        os.makedirs(torrent_dir, exist_ok=True)

        torrent_path = os.path.join(torrent_dir, '{}.{}'.format(
            torrent.id, secure_filename(torrent_file.filename)))
        torrent_file.save(torrent_path)
    torrent_file.close()

    return torrent


def _delete_info_dict(torrent):
    info_dict_path = torrent.info_dict_path
    if os.path.exists(info_dict_path):
        os.remove(info_dict_path)

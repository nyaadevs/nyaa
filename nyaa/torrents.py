import functools
import os
from urllib.parse import quote, urlencode

import flask
from flask import current_app as app

from orderedset import OrderedSet

from nyaa import bencode

USED_TRACKERS = OrderedSet()


def read_trackers_from_file(file_object):
    USED_TRACKERS.clear()

    for line in file_object:
        line = line.strip()
        if line and not line.startswith('#'):
            USED_TRACKERS.add(line)
    return USED_TRACKERS


def read_trackers():
    tracker_list_file = os.path.join(app.config['BASE_DIR'], 'trackers.txt')

    if os.path.exists(tracker_list_file):
        with open(tracker_list_file, 'r') as in_file:
            return read_trackers_from_file(in_file)


def default_trackers():
    if not USED_TRACKERS:
        read_trackers()
    return USED_TRACKERS[:]


def get_trackers_and_webseeds(torrent):
    trackers = OrderedSet()
    webseeds = OrderedSet()

    # Our main one first
    main_announce_url = app.config.get('MAIN_ANNOUNCE_URL')
    if main_announce_url:
        trackers.add(main_announce_url)

    # then the user ones
    torrent_trackers = torrent.trackers  # here be webseeds too
    for torrent_tracker in torrent_trackers:
        tracker = torrent_tracker.tracker

        # separate potential webseeds
        if tracker.is_webseed:
            webseeds.add(tracker.uri)
        else:
            trackers.add(tracker.uri)

    # and finally our tracker list
    trackers.update(default_trackers())

    return list(trackers), list(webseeds)


def get_default_trackers():
    trackers = OrderedSet()

    # Our main one first
    main_announce_url = app.config.get('MAIN_ANNOUNCE_URL')
    if main_announce_url:
        trackers.add(main_announce_url)

    # and finally our tracker list
    trackers.update(default_trackers())

    return list(trackers)


@functools.lru_cache(maxsize=1024*4)
def _create_magnet(display_name, info_hash, max_trackers=5, trackers=None):
    # Unless specified, we just use default trackers
    if trackers is None:
        trackers = get_default_trackers()

    magnet_parts = [
        ('dn', display_name)
    ]
    magnet_parts.extend(
        ('tr', tracker_url)
        for tracker_url in trackers[:max_trackers]
    )

    return ''.join([
        'magnet:?xt=urn:btih:', info_hash,
        '&', urlencode(magnet_parts, quote_via=quote)
    ])


def create_magnet(torrent):
    # Since we accept both models.Torrents and ES objects,
    # we need to make sure the info_hash is a hex string
    info_hash = torrent.info_hash
    if isinstance(info_hash, (bytes, bytearray)):
        info_hash = info_hash.hex()

    return _create_magnet(torrent.display_name, info_hash)


def create_default_metadata_base(torrent, trackers=None, webseeds=None):
    if trackers is None or webseeds is None:
        db_trackers, db_webseeds = get_trackers_and_webseeds(torrent)

        trackers = db_trackers if trackers is None else trackers
        webseeds = db_webseeds if webseeds is None else webseeds

    metadata_base = {
        'created by': 'NyaaV2',
        'creation date': int(torrent.created_utc_timestamp),
        'comment': flask.url_for('torrents.view',
                                 torrent_id=torrent.id,
                                 _external=True)
        # 'encoding' : 'UTF-8' # It's almost always UTF-8 and expected, but if it isn't...
    }

    if len(trackers) > 0:
        metadata_base['announce'] = trackers[0]
    if len(trackers) > 1:
        # Yes, it's a list of lists with a single element inside.
        metadata_base['announce-list'] = [[tracker] for tracker in trackers]

    # Add webseeds
    if webseeds:
        metadata_base['url-list'] = webseeds

    return metadata_base


def create_bencoded_torrent(torrent, bencoded_info, metadata_base=None):
    ''' Creates a bencoded torrent metadata for a given torrent,
        optionally using a given metadata_base dict (note: 'info' key will be
        popped off the dict) '''
    if metadata_base is None:
        metadata_base = create_default_metadata_base(torrent)

    metadata_base['encoding'] = torrent.encoding

    # Make sure info doesn't exist on the base
    metadata_base.pop('info', None)
    prefixed_dict = {key: metadata_base[key] for key in metadata_base if key < 'info'}
    suffixed_dict = {key: metadata_base[key] for key in metadata_base if key > 'info'}

    prefix = bencode.encode(prefixed_dict)
    suffix = bencode.encode(suffixed_dict)

    bencoded_torrent = prefix[:-1] + b'4:info' + bencoded_info + suffix[1:]

    return bencoded_torrent

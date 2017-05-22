import os
import base64
import time
from urllib.parse import urlencode
from orderedset import OrderedSet
from nyaa import app

from nyaa import bencode
from nyaa import app
from nyaa import models

USED_TRACKERS = OrderedSet()

# Limit the amount of trackers added into .torrent files
MAX_TRACKERS = 5


def read_trackers_from_file(file_object):
    USED_TRACKERS.clear()

    for line in file_object:
        line = line.strip()
        if line:
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


def get_trackers(torrent):
    trackers = OrderedSet()

    # Our main one first
    main_announce_url = app.config.get('MAIN_ANNOUNCE_URL')
    if main_announce_url:
        trackers.add(main_announce_url)

    # then the user ones
    torrent_trackers = torrent.trackers
    for torrent_tracker in torrent_trackers:
        trackers.add(torrent_tracker.tracker.uri)

    # and finally our tracker list
    trackers.update(default_trackers())

    return list(trackers)


def get_trackers_magnet():
    trackers = OrderedSet()

    # Our main one first
    main_announce_url = app.config.get('MAIN_ANNOUNCE_URL')
    if main_announce_url:
        trackers.add(main_announce_url)

    # and finally our tracker list
    trackers.update(default_trackers())

    return list(trackers)


def create_magnet(torrent, max_trackers=5, trackers=None):
    if trackers is None:
        trackers = get_trackers_magnet()

    magnet_parts = [
        ('dn', torrent.display_name)
    ]
    for tracker in trackers[:max_trackers]:
        magnet_parts.append(('tr', tracker))

    b32_info_hash = base64.b32encode(torrent.info_hash).decode('utf-8')
    return 'magnet:?xt=urn:btih:' + b32_info_hash + '&' + urlencode(magnet_parts)


# For processing ES links
@app.context_processor
def create_magnet_from_info():
    def _create_magnet_from_info(display_name, info_hash, max_trackers=5, trackers=None):
        if trackers is None:
            trackers = get_trackers_magnet()

        magnet_parts = [
            ('dn', display_name)
        ]
        for tracker in trackers[:max_trackers]:
            magnet_parts.append(('tr', tracker))

        b32_info_hash = base64.b32encode(bytes.fromhex(info_hash)).decode('utf-8')
        return 'magnet:?xt=urn:btih:' + b32_info_hash + '&' + urlencode(magnet_parts)
    return dict(create_magnet_from_info=_create_magnet_from_info)


def create_default_metadata_base(torrent, trackers=None):
    if trackers is None:
        trackers = get_trackers(torrent)

    metadata_base = {
        'created by': 'NyaaV2',
        'creation date': int(time.time()),
        'comment': 'NyaaV2 Torrent #' + str(torrent.id),  # Throw the url here or something neat
        # 'encoding' : 'UTF-8' # It's almost always UTF-8 and expected, but if it isn't...
    }

    if len(trackers) > 0:
        metadata_base['announce'] = trackers[0]
    if len(trackers) > 1:
        # Yes, it's a list of lists with a single element inside.
        metadata_base['announce-list'] = [[tracker] for tracker in trackers[:MAX_TRACKERS]]

    return metadata_base


def create_bencoded_torrent(torrent, metadata_base=None):
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

    bencoded_info = torrent.info.info_dict
    bencoded_torrent = prefix[:-1] + b'4:info' + bencoded_info + suffix[1:]

    return bencoded_torrent

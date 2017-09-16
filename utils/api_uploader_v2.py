#!/usr/bin/env python3
import argparse
import json
import os

import requests

NYAA_HOST = 'https://nyaa.si'
SUKEBEI_HOST = 'https://sukebei.nyaa.si'

API_BASE = '/api'
API_UPLOAD = API_BASE + '/upload'

NYAA_CATS = '''1_1 - Anime - AMV
1_2 - Anime - English
1_3 - Anime - Non-English
1_4 - Anime - Raw
2_1 - Audio - Lossless
2_2 - Audio - Lossy
3_1 - Literature - English-translated
3_2 - Literature - Non-English
3_3 - Literature - Non-English-Translated
3_4 - Literature - Raw
4_1 - Live Action - English-translated
4_2 - Live Action - Idol/Promotional Video
4_3 - Live Action - Non-English-translated
4_4 - Live Action - Raw
5_1 - Pictures - Graphics
5_2 - Pictures - Photos
6_1 - Software - Applications
6_2 - Software - Games'''

SUKEBEI_CATS = '''1_1 - Art - Anime
1_2 - Art - Doujinshi
1_3 - Art - Games
1_4 - Art - Manga
1_5 - Art - Pictures
2_1 - Real Life - Photobooks / Pictures
2_2 - Real Life - Videos'''


class CategoryPrintAction(argparse.Action):
    def __init__(self, option_strings, nargs='?', help=None, **kwargs):
        super().__init__(option_strings=option_strings,
                         dest='site',
                         default=None,
                         nargs=nargs,
                         help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        if values and values.lower() == 'sukebei':
            print("Sukebei categories")
            print(SUKEBEI_CATS)
        else:
            print("Nyaa categories")
            print(NYAA_CATS)
        parser.exit()


environment_epillog = ('You may also provide environment variables NYAA_API_HOST, NYAA_API_USERNAME'
                       ' and NYAA_API_PASSWORD for connection info.')

parser = argparse.ArgumentParser(
    description='Upload torrents to Nyaa.si', epilog=environment_epillog)

parser.add_argument('--list-categories', default=False, action=CategoryPrintAction, nargs='?',
                    help='List torrent categories. Include "sukebei" to show Sukebei categories')

conn_group = parser.add_argument_group('Connection options')

conn_group.add_argument('-s', '--sukebei', default=False,
                        action='store_true', help='Upload to sukebei.nyaa.si')

conn_group.add_argument('-u', '--user', help='Username or email')
conn_group.add_argument('-p', '--password', help='Password')
conn_group.add_argument('--host', help='Select another api host (for debugging purposes)')

resp_group = parser.add_argument_group('Response options')

resp_group.add_argument('--raw', default=False, action='store_true',
                        help='Print only raw response (JSON)')
resp_group.add_argument('-m', '--magnet', default=False,
                        action='store_true', help='Print magnet uri')

tor_group = parser.add_argument_group('Torrent options')

tor_group.add_argument('-c', '--category', required=True, help='Torrent category (see ). Required.')
tor_group.add_argument('-n', '--name', help='Display name for the torrent (optional)')
tor_group.add_argument('-i', '--information', help='Information field (optional)')
tor_group.add_argument('-d', '--description', help='Description for the torrent (optional)')
tor_group.add_argument('-D', '--description-file', metavar='FILE',
                       help='Read description from a file (optional)')

tor_group.add_argument('-A', '--anonymous', default=False,
                       action='store_true', help='Upload torrent anonymously')
tor_group.add_argument('-H', '--hidden', default=False, action='store_true',
                       help='Hide torrent from results')
tor_group.add_argument('-C', '--complete', default=False, action='store_true',
                       help='Mark torrent as complete (eg. season batch)')
tor_group.add_argument('-R', '--remake', default=False, action='store_true',
                       help='Mark torrent as remake (derivative work from another release)')

trusted_group = tor_group.add_mutually_exclusive_group(required=False)
trusted_group.add_argument('-T', '--trusted', dest='trusted', action='store_true',
                           help='Mark torrent as trusted, if possible. Defaults to true')
trusted_group.add_argument('--no-trusted', dest='trusted',
                           action='store_false', help='Do not mark torrent as trusted')
parser.set_defaults(trusted=True)

tor_group.add_argument('torrent', metavar='TORRENT_FILE', help='The .torrent file to upload')


def crude_torrent_check(file_object):
    ''' Does a simple check to weed out accidentally picking a wrong file '''
    # Check if file seems to be a bencoded dictionary: starts with d and end with e
    file_object.seek(0)
    if file_object.read(1) != b'd':
        return False

    file_object.seek(-1, os.SEEK_END)
    if file_object.read(1) != b'e':
        return False

    # Seek back to beginning
    file_object.seek(0)

    return True


if __name__ == "__main__":
    args = parser.parse_args()

    # Use debug host from args or environment, if set
    debug_host = args.host or os.getenv('NYAA_API_HOST')
    api_host = (debug_host or (args.sukebei and SUKEBEI_HOST or NYAA_HOST)).rstrip('/')

    api_upload_url = api_host + API_UPLOAD

    if args.description_file:
        # Replace args.description with contents of the file
        with open(args.description_file, 'r') as in_file:
            args.description = in_file.read()

    torrent_file = open(args.torrent, 'rb')
    # Check if the file even seems like a torrent
    if not crude_torrent_check(torrent_file):
        raise Exception("File '{}' doesn't seem to be a torrent file".format(args.torrent))

    api_username = args.user or os.getenv('NYAA_API_USERNAME')
    api_password = args.password or os.getenv('NYAA_API_PASSWORD')

    if not (api_username and api_password):
        raise Exception('No authorization found from arguments or environment variables.')

    auth = (api_username, api_password)

    data = {
        'name': args.name,
        'category': args.category,

        'information': args.information,
        'description': args.description,

        'anonymous': args.anonymous,
        'hidden': args.hidden,
        'complete': args.complete,
        'remake': args.remake,
        'trusted': args.trusted,
    }
    encoded_data = {
        'torrent_data': json.dumps(data)
    }

    files = {
        'torrent': torrent_file
    }

    # Go!
    r = requests.post(api_upload_url, auth=auth, data=encoded_data, files=files)
    torrent_file.close()

    if args.raw:
        print(r.text)

    else:
        try:
            response = r.json()
        except ValueError:
            print('Bad response:')
            print(r.text)
            exit(1)

        errors = response.get('errors')
        if errors:
            print('Upload failed', errors)
            exit(1)
        else:
            print("[Uploaded] {url} - '{name}'".format(**response))
            if args.magnet:
                print(response['magnet'])

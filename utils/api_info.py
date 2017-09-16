#!/usr/bin/env python3
import argparse
import os
import re

import requests

NYAA_HOST = 'https://nyaa.si'
SUKEBEI_HOST = 'https://sukebei.nyaa.si'

API_BASE = '/api'
API_INFO = API_BASE + '/info'

ID_PATTERN = '^[0-9]+$'
INFO_HASH_PATTERN = '^[0-9a-fA-F]{40}$'

environment_epillog = ('You may also provide environment variables NYAA_API_HOST, NYAA_API_USERNAME'
                       ' and NYAA_API_PASSWORD for connection info.')

parser = argparse.ArgumentParser(
    description='Query torrent info on Nyaa.si', epilog=environment_epillog)

conn_group = parser.add_argument_group('Connection options')

conn_group.add_argument('-s', '--sukebei', default=False,
                        action='store_true', help='Query torrent info on sukebei.Nyaa.si')

conn_group.add_argument('-u', '--user', help='Username or email')
conn_group.add_argument('-p', '--password', help='Password')
conn_group.add_argument('--host', help='Select another api host (for debugging purposes)')

resp_group = parser.add_argument_group('Response options')

resp_group.add_argument('--raw', default=False, action='store_true',
                        help='Print only raw response (JSON)')
resp_group.add_argument('-m', '--magnet', default=False,
                        action='store_true', help='Print magnet uri')


req_group = parser.add_argument_group('Required arguments')
req_group.add_argument('hash_or_id', metavar='HASH_OR_ID',
                       help='Torrent ID or hash (hex, 40 characters) to query for')


def easy_file_size(filesize):
    for prefix in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
        if filesize < 1024.0:
            return '{0:.1f} {1}'.format(filesize, prefix)
        filesize = filesize / 1024.0
    return '{0:.1f} {1}'.format(filesize, prefix)


def _as_yes_no(value):
    return 'Yes' if value else 'No'


INFO_TEMPLATE = ("Torrent #{id}: '{name}' ({formatted_filesize}) uploaded by {submitter}"
                 "\n  {creation_date} [{main_category} - {sub_category}] [{flag_info}]")
FLAG_NAMES = ['Trusted', 'Complete', 'Remake']


if __name__ == '__main__':
    args = parser.parse_args()

    # Use debug host from args or environment, if set
    debug_host = args.host or os.getenv('NYAA_API_HOST')
    api_host = (debug_host or (args.sukebei and SUKEBEI_HOST or NYAA_HOST)).rstrip('/')

    api_query = args.hash_or_id.lower().strip()

    # Verify query is either a valid id or valid hash
    id_match = re.match(ID_PATTERN, api_query)
    hex_hash_match = re.match(INFO_HASH_PATTERN, api_query)

    if not (id_match or hex_hash_match):
        raise Exception("Given argument '{}' doesn't "
                        "seem like an ID or a hex hash.".format(api_query))

    if id_match:
        # Remove leading zeroes
        api_query = api_query.lstrip('0')

    api_info_url = api_host + API_INFO + '/' + api_query

    api_username = args.user or os.getenv('NYAA_API_USERNAME')
    api_password = args.password or os.getenv('NYAA_API_PASSWORD')

    if not (api_username and api_password):
        raise Exception('No authorization found from arguments or environment variables.')

    auth = (api_username, api_password)

    # Go!
    r = requests.get(api_info_url, auth=auth)

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
            print('Info request failed:', errors)
            exit(1)
        else:
            formatted_filesize = easy_file_size(response.get('filesize', 0))
            flag_info = ', '.join(
                n + ': ' + _as_yes_no(response['is_' + n.lower()]) for n in FLAG_NAMES)

            info_str = INFO_TEMPLATE.format(formatted_filesize=formatted_filesize,
                                            flag_info=flag_info, **response)

            print(info_str)
            if args.magnet:
                print(response['magnet'])

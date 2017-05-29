#!/usr/bin/env python3

import re
import os
import argparse
import requests
import json
from pprint import pprint

DEV_HOST = 'http://127.0.0.1:5500'
NYAA_HOST = 'https://nyaa.si'
SUKEBEI_HOST = 'https://sukebei.nyaa.si'

API_BASE = '/api'
API_INFO = API_BASE + '/info'

ID_PATTERN = '^[1-9][0-9]*$'
INFO_HASH_PATTERN = '^[0-9a-fA-F]{40}$'

environment_epillog = '''You may also provide environment variables NYAA_API_HOST, NYAA_API_USERNAME and NYAA_API_PASSWORD for connection info.'''

parser = argparse.ArgumentParser(description='Query torrent info on Nyaa.si', epilog=environment_epillog)

conn_group = parser.add_argument_group('Connection options')

conn_group.add_argument('-s', '--sukebei', default=False, action='store_true', help='Upload to sukebei.nyaa.si')

conn_group.add_argument('-u', '--user', help='Username or email')
conn_group.add_argument('-p', '--password', help='Password')
conn_group.add_argument('--host', help='Select another api host (for debugging purposes)')

parser.add_argument('-q', '--query', required=True, help='Torrent by id or hash Required.')

if __name__ == '__main__':
    args = parser.parse_args()

    # Use debug host from args or environment, if set
    debug_host = args.host or os.getenv('NYAA_API_HOST')
    api_host = (debug_host or (args.sukebei and SUKEBEI_HOST or NYAA_HOST)).rstrip('/')

    api_query = args.query.lower().strip()

    # Verify query is either a valid id or valid hash
    matchID = re.match(ID_PATTERN, api_query)
    matchHASH = re.match(INFO_HASH_PATTERN, api_query)

    if not (matchID or matchHASH):
        raise Exception('Query was not a valid id or valid hash.')


    api_info_url = api_host + API_INFO + '/' + api_query

    api_username = args.user     or os.getenv('NYAA_API_USERNAME')
    api_password = args.password or os.getenv('NYAA_API_PASSWORD')

    if not (api_username and api_password):
        raise Exception('No authorization found from arguments or environment variables.')

    auth = (api_username, api_password)

    # Go!
    r = requests.get(api_info_url, auth=auth)

    #print(r.text)

    # For printing unicode instead of unicode escape sequences
    jr = json.loads(r.text)
    pprint(jr)

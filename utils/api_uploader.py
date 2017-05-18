# Uploads a single torrent file
# Works on nyaa.si and sukebei.nyaa.si

import json
import requests

'''
The POST payload to the api endpoint (/api/upload) should be multipart/form-data containing three fields

'auth_info': file containing "{
    'username': str,
    'password': str
}",

'torrent_info':  {
    'category': str, # see below
    'display_name': str, # optional
    'information': str,
    'description': str,
    'is_anonymous': boolean,
    'is_hidden': boolean,
    'is_remake': boolean,
    'is_complete': boolean
},

'torrent_file': multi part file format


A successful request should return {'Success': int(torrent_id)}
A failed request should return {'Failure': ["Failure 1", "Failure 2"...]]}

'''

# ########################################### HELP ############################################
# ################################# CATEGORIES MUST BE EXACT ##################################
'''
# Nyaa categories only for now, but api still works for sukebei

Anime
    Anime - AMV                          : '1_1'
    Anime - English                      : '1_2'
    Anime - Non-English                  : '1_3'
    Anime - Raw                          : '1_4'
Audio
    Lossless                             : '2_1'
    Lossy                                : '2_2'
Literature
    Literature - English-translated      : '3_1'
    Literature - Non-English             : '3_2'
    Literature - Non-English-Translated  : '3_3'
    Literature - Raw                     : '3_4'
Live Action
    Live Action - English-translated     : '4_1'
    Live Action - Idol/Promotional Video : '4_2'
    Live Action - Non-English-translated : '4_3'
    Live Action - Raw                    : '4_4'
Pictures
    Pictures - Graphics                  : '5_1'
    Pictures - Photos                    : '5_2'
Software
    Software - Applications              : '6_1'
    Software - Games                     : '6_2'
'''
# ################################# CATEGORIES MUST BE EXACT ##################################

# ###################################### EXAMPLE REQUEST ######################################
'''
# Required
username = ''
password = ''
torrent_file = '/path/to/my.torrent'
category = '1_2'

#Optional
display_name = ''
information = 'API HOWTO'
description = 'Visit #nyaa-dev@irc.rizon.net'

# Defaults to False, change to True to set
is_anonymous : False,
is_hidden    : False,
is_remake    : False,
is_complete  : False
'''


# ######################################## CHANGE HERE ########################################

url = 'https://nyaa.si/api/upload'  # or https://sukebei.nyaa.si/api/upload or http://127.0.0.1:5500/api/upload

# Required
username = ''
password = ''
torrent_file = ''
category = ''

# Optional
display_name = ''
information  = ''
description  = ''
is_anonymous = False
is_hidden    = False
is_remake    = False
is_complete  = False

auth_info = {
    'username'     : username,
    'password'     : password
}

metadata={
    'category'     : category,
    'display_name' : display_name,
    'information'  : information,
    'description'  : description,
    'is_anonymous' : is_anonymous,
    'is_hidden'    : is_hidden,
    'is_remake'    : is_remake,
    'is_complete'  : is_complete
}

files = {
    'auth_info'    : (json.dumps(auth_info)),
    'torrent_info' : (json.dumps(metadata)),
    'torrent_file' : ('{0}'.format(torrent_file), open(torrent_file, 'rb'), 'application/octet-stream')
}

response = requests.post(url, files=files)
json_response = response.json()
print(json_response)
# A successful request should print {'Success': int(torrent_id)}
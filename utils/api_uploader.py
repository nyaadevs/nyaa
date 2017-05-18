# Uploads a single torrent file
# Works on nyaa.si
# An updated version will work on sukebei.nyaa.si

import json
# pip install requests
# http://docs.python-requests.org/en/master/user/install/
import requests

#url = "http://127.0.0.1:5500/api/upload"
url = "https://nyaa.si/api/upload"

# ########################## REQUIRED: YOUR USERNAME AND PASSWORD ##############################
username = ""
password = ""

# ########################################### HELP ############################################

# ################################# CATEGORIES MUST BE EXACT ##################################
"""
Anime
    Anime - AMV                          : "1_1"
    Anime - English                      : "1_2"
    Anime - Non-English                  : "1_3"
    Anime - Raw                          : "1_4"
Audio
    Lossless                             : "2_1"
    Lossy                                : "2_2"
Literature
    Literature - English-translated      : "3_1"
    Literature - Non-English             : "3_2"
    Literature - Non-English-Translated  : "3_3"
    Literature - Raw                     : "3_4"
Live Action
    Live Action - English-translated     : "4_1"
    Live Action - Idol/Promotional Video : "4_2"
    Live Action - Non-English-translated : "4_3"
    Live Action - Raw                    : "4_4"
Pictures
    Pictures - Graphics                  : "5_1"
    Pictures - Photos                    : "5_2"
Software
    Software - Applications              : "6_1"
    Software - Games                     : "6_2"
"""
# ################################# CATEGORIES MUST BE EXACT ##################################

# ###################################### EXAMPLE REQUEST ######################################
"""
# Required
file_name = "/path/to/my_file.torrent"
# Required
category = "6_1"
# Required
display_name = "API upload example"

# May be blank
information = "API HOWTO"
# May be blank
description = "Visit #nyaa-dev@irc.rizon.net"
# Default is 'n' No
# Change to 'y' Yes to set
is_anonymous : 'n',
is_hidden    : 'n',
is_remake    : 'n',
is_complete  : 'n'
"""
# #############################################################################################

# ######################################## CHANGE HERE ########################################
# Required
file_name = ""
# Required
category = ""
# Required
display_name = ""

# May be blank
information = ""
# May be blank
description = ""
# Default is 'n' No
# Change to 'y' Yes to set
is_anonymous = 'n'
is_hidden    = 'n'
is_remake    = 'n'
is_complete  = 'n'
# #############################################################################################

# #################################### DO NOT CHANGE BELOW ####################################
# ############################ UNLESS YOU KNOW WHAT YOU ARE DOING #############################
auth_info = {
    "username"     : username,
    "password"     : password
}

metadata={
    "category"     : category,
    "display_name" : display_name,
    "information"  : information,
    "description"  : description,
    "is_anonymous" : is_anonymous,
    "is_hidden"    : is_hidden,
    "is_remake"    : is_remake,
    "is_complete"  : is_complete
}

files = {
    'auth_info'    : (json.dumps(auth_info)),
    'torrent_info' : (json.dumps(metadata)),
    'torrent_file' : ('{0}'.format(file_name), open(file_name, 'rb'), 'application/octet-stream')
}

response = requests.post(url, files=files)

json_response = response.json()

print(json_response)

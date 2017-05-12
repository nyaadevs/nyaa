# api_uploader.py


# Uploads a single file
# I will create another script for batch uploading

import json
import requests

url = "http://127.0.0.1:5500/api/upload"

# Required for Auth
username = ""
password = ""

# Required
torrent_name = ""

# Required
main_cat = ""
# Required
sub_cat = ""

# May be blank
information = ""
# May be blank
description = ""
# flags = [Hidden, Remake, Complete, Anonymous]
# 0 for NOT SET / 1 for SET
# Required
flags = [0, 0, 0, 0]

metadata={
    "username": username,
    "password": password,
    "display_name": torrent_name,
    "main_cat": main_cat,
    "sub_cat": sub_cat,
    "information": information,
    "description": description,
    "flags": flags
    }

# Required
file_name = ""

files = {
    'json': (json.dumps(metadata)),
    'torrent': ('{0}'.format(file_name), open(file_name, 'rb'), 'application/octet-stream')}

response = requests.post(url, files=files)

json_response = response.json()

print(json_response)

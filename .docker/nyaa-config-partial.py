# This is only a partial config file that will be appended to the end of
# config.example.py to build the full config for the docker environment

SITE_NAME = 'Nyaa [DEVEL]'
GLOBAL_SITE_NAME = 'nyaa.devel'
SQLALCHEMY_DATABASE_URI = ('mysql://nyaadev:ZmtB2oihHFvc39JaEDoF@mariadb/nyaav2?charset=utf8mb4')
# MAIN_ANNOUNCE_URL = 'http://chihaya:6881/announce'
# TRACKER_API_URL = 'http://chihaya:6881/api'
BACKUP_TORRENT_FOLDER = '/nyaa-torrents'
ES_HOSTS = ['elasticsearch:9200']

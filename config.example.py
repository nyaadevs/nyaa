import os


DEBUG = True
USE_RECAPTCHA = False
USE_EMAIL_VERIFICATION = False
USE_MYSQL = True

# Enable this once stat integration is done
ENABLE_SHOW_STATS = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if USE_MYSQL:
    SQLALCHEMY_DATABASE_URI = ('mysql://test:test123@localhost/nyaav2')
else:
    SQLALCHEMY_DATABASE_URI = (
        'sqlite:///' + os.path.join(BASE_DIR, 'test.db') + '?check_same_thread=False')

CSRF_SESSION_KEY = '***'
SECRET_KEY = '***'

# Prefix for running multiple sites, user table will not be prefixed.
SITE_FLAVOR = 'nyaa' # 'nyaa' or 'sukebei'
TABLE_PREFIX = SITE_FLAVOR + '_'

# for recaptcha and email verification:
# keys for localhost. Change as appropriate when actual domain is registered.
RECAPTCHA_PUBLIC_KEY = '***'
RECAPTCHA_PRIVATE_KEY = '***'
SMTP_SERVER = '***'
SMTP_PORT = 587
MAIL_FROM_ADDRESS = '***'
SMTP_USERNAME = '***'
SMTP_PASSWORD = '***'

RESULTS_PER_PAGE = 75

# What the site identifies itself as.
SITE_NAME = 'Nyaa'

# The maximum number of files a torrent can contain
# until the site says "Too many files to display."
MAX_FILES_VIEW = 1000

# """
# Setting to make sure main announce url is present in torrent
# """
ENFORCE_MAIN_ANNOUNCE_URL = False
MAIN_ANNOUNCE_URL = ''

BACKUP_TORRENT_FOLDER = 'torrents'

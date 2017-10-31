import os

DEBUG = True

######################
## Maintenance mode ##
######################

# A read-only maintenance mode, in which the database is not modified
MAINTENANCE_MODE = False
# A maintenance message (used in layout.html template)
MAINTENANCE_MODE_MESSAGE = 'Site is currently in read-only maintenance mode.'
# Allow logging in during maintenance (without updating last login date)
MAINTENANCE_MODE_LOGINS = True

#############
## General ##
#############

# What the site identifies itself as. This affects templates, not database stuff.
SITE_NAME = 'Nyaa'
# What the both sites are labeled under (used for eg. email subjects)
GLOBAL_SITE_NAME = 'Nyaa.si'

# General prefix for running multiple sites, eg. most database tables are site-prefixed
SITE_FLAVOR = 'nyaa' # 'nyaa' or 'sukebei'
# Full external urls to both sites, used for site-change links
EXTERNAL_URLS = {'fap':'***', 'main':'***'}

# Secret keys for Flask
CSRF_SESSION_KEY = '***'
SECRET_KEY = '***'

# Present a recaptcha for anonymous uploaders
USE_RECAPTCHA = False
# Require email validation
USE_EMAIL_VERIFICATION = False
# Use MySQL or Sqlite3 (mostly deprecated)
USE_MYSQL = True
# Show seeds/peers/completions in torrent list/page
ENABLE_SHOW_STATS = True

# Enable password recovery (by reset link to given email address)
# Depends on email support!
ALLOW_PASSWORD_RESET = True

# Recaptcha keys (https://www.google.com/recaptcha)
RECAPTCHA_PUBLIC_KEY = '***'
RECAPTCHA_PRIVATE_KEY = '***'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if USE_MYSQL:
    SQLALCHEMY_DATABASE_URI = ('mysql://test:test123@localhost/nyaav2?charset=utf8mb4')
else:
    SQLALCHEMY_DATABASE_URI = (
        'sqlite:///' + os.path.join(BASE_DIR, 'test.db') + '?check_same_thread=False')

###########
## EMAIL ##
###########

# 'smtp' or 'mailgun'
MAIL_BACKEND = 'mailgun'
MAIL_FROM_ADDRESS = 'Sender Name <sender@domain.com>'

# Mailgun settings
MAILGUN_API_BASE = 'https://api.mailgun.net/v3/YOUR_DOMAIN_NAME'
MAILGUN_API_KEY = 'YOUR_API_KEY'

# SMTP settings
SMTP_SERVER = '***'
SMTP_PORT = 587
SMTP_USERNAME = '***'
SMTP_PASSWORD = '***'


# The maximum number of files a torrent can contain
# until the site says "Too many files to display."
MAX_FILES_VIEW = 1000

# Verify uploaded torrents have the given tracker in them?
ENFORCE_MAIN_ANNOUNCE_URL = False
MAIN_ANNOUNCE_URL = 'http://127.0.0.1:6881/announce'

# Tracker API integration - don't mind this
TRACKER_API_URL = 'http://127.0.0.1:6881/api'
TRACKER_API_AUTH = 'topsecret'

#############
## Account ##
#############

# Limit torrent upload rate
RATELIMIT_UPLOADS = True
RATELIMIT_ACCOUNT_AGE = 7 * 24 * 3600
# After uploading MAX_UPLOAD_BURST torrents within UPLOAD_BURST_DURATION,
# the following uploads must be at least UPLOAD_TIMEOUT seconds after the previous upload.
MAX_UPLOAD_BURST = 5
UPLOAD_BURST_DURATION = 45 * 60
UPLOAD_TIMEOUT = 15 * 60

# Torrents uploaded without an account must be at least this big in total (bytes)
# Set to 0 to disable
MINIMUM_ANONYMOUS_TORRENT_SIZE = 1 * 1024 * 1024

# Minimum age for an account not to be served a captcha (seconds)
# Relies on USE_RECAPTCHA. Set to 0 to disable.
ACCOUNT_RECAPTCHA_AGE = 7 * 24 * 3600  # A week

# Backup original .torrent uploads
BACKUP_TORRENT_FOLDER = 'torrents'

############
## Search ##
############

# How many results should a page contain. Applies to RSS as well.
RESULTS_PER_PAGE = 75

# Use better searching with ElasticSearch
# See README.MD on setup!
USE_ELASTIC_SEARCH = False
# Highlight matches (for debugging)
ENABLE_ELASTIC_SEARCH_HIGHLIGHT = False

# Max ES search results, do not set over 10000
ES_MAX_SEARCH_RESULT = 1000
# ES index name generally (nyaa or sukebei)
ES_INDEX_NAME = SITE_FLAVOR

################
## Commenting ##
################

# Time limit for editing a comment after it has been posted (seconds)
# Set to 0 to disable
EDITING_TIME_LIMIT = 0

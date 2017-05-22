import flask
from enum import Enum, IntEnum
from datetime import datetime, timezone
from nyaa import app, db
from nyaa.torrents import create_magnet
from sqlalchemy import func, ForeignKeyConstraint, Index
from sqlalchemy_utils import ChoiceType, EmailType, PasswordType
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_fulltext import FullText
from ipaddress import ip_address

import re
import base64
from markupsafe import escape as escape_markup
from urllib.parse import urlencode, unquote as unquote_url
from hashlib import md5

if app.config['USE_MYSQL']:
    from sqlalchemy.dialects import mysql
    BinaryType = mysql.BINARY
    DescriptionTextType = mysql.TEXT
    MediumBlobType = mysql.MEDIUMBLOB
    COL_UTF8_GENERAL_CI = 'utf8_general_ci'
    COL_UTF8MB4_BIN = 'utf8mb4_bin'
    COL_ASCII_GENERAL_CI = 'ascii_general_ci'
else:
    BinaryType = db.Binary
    DescriptionTextType = db.String
    MediumBlobType = db.BLOB
    COL_UTF8_GENERAL_CI = 'NOCASE'
    COL_UTF8MB4_BIN = None
    COL_ASCII_GENERAL_CI = 'NOCASE'


# For property timestamps
UTC_EPOCH = datetime.utcfromtimestamp(0)


class TorrentFlags(IntEnum):
    NONE = 0
    ANONYMOUS = 1
    HIDDEN = 2
    TRUSTED = 4
    REMAKE = 8
    COMPLETE = 16
    DELETED = 32


DB_TABLE_PREFIX = app.config['TABLE_PREFIX']


class Torrent(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'torrents'

    id = db.Column(db.Integer, primary_key=True)
    info_hash = db.Column(BinaryType(length=20), unique=True, nullable=False, index=True)
    display_name = db.Column(
        db.String(length=255, collation=COL_UTF8_GENERAL_CI), nullable=False, index=True)
    torrent_name = db.Column(db.String(length=255), nullable=False)
    information = db.Column(db.String(length=255), nullable=False)
    description = db.Column(DescriptionTextType(collation=COL_UTF8MB4_BIN), nullable=False)

    filesize = db.Column(db.BIGINT, default=0, nullable=False, index=True)
    encoding = db.Column(db.String(length=32), nullable=False)
    flags = db.Column(db.Integer, default=0, nullable=False, index=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploader_ip = db.Column(db.Binary(length=16), default=None, nullable=True)
    has_torrent = db.Column(db.Boolean, nullable=False, default=False)

    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime(timezone=False),
                             default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    main_category_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'main_categories.id'), nullable=False)
    sub_category_id = db.Column(db.Integer, nullable=False)
    redirect = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id'), nullable=True)

    __table_args__ = (
        Index('uploader_flag_idx', 'uploader_id', 'flags'),
        ForeignKeyConstraint(
            ['main_category_id', 'sub_category_id'],
            [DB_TABLE_PREFIX + 'sub_categories.main_category_id',
                DB_TABLE_PREFIX + 'sub_categories.id']
        ), {}
    )

    user = db.relationship('User', uselist=False, back_populates='torrents')
    main_category = db.relationship('MainCategory', uselist=False,
                                    back_populates='torrents', lazy="joined")
    sub_category = db.relationship('SubCategory', uselist=False, backref='torrents', lazy="joined",
                                   primaryjoin=(
                                       "and_(SubCategory.id == foreign(Torrent.sub_category_id), "
                                       "SubCategory.main_category_id == Torrent.main_category_id)"))
    info = db.relationship('TorrentInfo', uselist=False,
                           cascade="all, delete-orphan", back_populates='torrent')
    filelist = db.relationship('TorrentFilelist', uselist=False,
                               cascade="all, delete-orphan", back_populates='torrent')
    stats = db.relationship('Statistic', uselist=False,
                            cascade="all, delete-orphan", back_populates='torrent', lazy='joined')
    trackers = db.relationship('TorrentTrackers', uselist=True,
                               cascade="all, delete-orphan", lazy='joined')
    comments = db.relationship('Comment', uselist=True,
                               cascade="all, delete-orphan")

    def __repr__(self):
        return '<{0} #{1.id} \'{1.display_name}\' {1.filesize}b>'.format(type(self).__name__, self)

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @property
    def information_as_link(self):
        ''' Formats the .information into an IRC or HTTP(S) <a> if possible,
            otherwise escapes it. '''
        irc_match = re.match(r'^#([a-zA-Z0-9-_]+)@([a-zA-Z0-9-_.:]+)$', self.information)
        if irc_match:
            # Return a formatted IRC uri
            return '<a href="irc://{1}/{0}">#{0}@{1}</a>'.format(*irc_match.groups())

        url_match = re.match(r'^(https?:\/\/.+?)$', self.information)
        if url_match:
            url = url_match.group(1)

            invalid_url_characters = '<>"'
            # Check if url contains invalid characters
            if not any(c in url for c in invalid_url_characters):
                return '<a href="{0}">{1}</a>'.format(url, escape_markup(unquote_url(url)))
        # Escaped
        return escape_markup(self.information)

    @property
    def info_hash_as_b32(self):
        return base64.b32encode(self.info_hash).decode('utf-8')

    @property
    def info_hash_as_hex(self):
        return self.info_hash.hex()

    @property
    def magnet_uri(self):
        return create_magnet(self)

    @property
    def uploader_ip_string(self):
        if self.uploader_ip:
            return str(ip_address(self.uploader_ip))

    @property
    def anonymous(self):
        return self.flags & TorrentFlags.ANONYMOUS

    @anonymous.setter
    def anonymous(self, value):
        self.flags = (self.flags & ~TorrentFlags.ANONYMOUS) | (value and TorrentFlags.ANONYMOUS)

    @property
    def hidden(self):
        return self.flags & TorrentFlags.HIDDEN

    @hidden.setter
    def hidden(self, value):
        self.flags = (self.flags & ~TorrentFlags.HIDDEN) | (value and TorrentFlags.HIDDEN)

    @property
    def deleted(self):
        return self.flags & TorrentFlags.DELETED

    @deleted.setter
    def deleted(self, value):
        self.flags = (self.flags & ~TorrentFlags.DELETED) | (value and TorrentFlags.DELETED)

    @property
    def trusted(self):
        return self.flags & TorrentFlags.TRUSTED

    @trusted.setter
    def trusted(self, value):
        self.flags = (self.flags & ~TorrentFlags.TRUSTED) | (value and TorrentFlags.TRUSTED)

    @property
    def remake(self):
        return self.flags & TorrentFlags.REMAKE

    @remake.setter
    def remake(self, value):
        self.flags = (self.flags & ~TorrentFlags.REMAKE) | (value and TorrentFlags.REMAKE)

    @property
    def complete(self):
        return self.flags & TorrentFlags.COMPLETE

    @complete.setter
    def complete(self, value):
        self.flags = (self.flags & ~TorrentFlags.COMPLETE) | (value and TorrentFlags.COMPLETE)

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def by_info_hash(cls, info_hash):
        return cls.query.filter_by(info_hash=info_hash).first()


class TorrentNameSearch(FullText, Torrent):
    __fulltext_columns__ = ('display_name',)


class TorrentFilelist(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'torrents_filelist'
    __table_args__ = {'mysql_row_format': 'COMPRESSED'}

    torrent_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id', ondelete="CASCADE"), primary_key=True)
    filelist_blob = db.Column(MediumBlobType, nullable=True)

    torrent = db.relationship('Torrent', uselist=False, back_populates='filelist')


class TorrentInfo(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'torrents_info'
    __table_args__ = {'mysql_row_format': 'COMPRESSED'}

    torrent_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id', ondelete="CASCADE"), primary_key=True)
    info_dict = db.Column(MediumBlobType, nullable=True)

    torrent = db.relationship('Torrent', uselist=False, back_populates='info')


class Statistic(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'statistics'

    torrent_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id', ondelete="CASCADE"), primary_key=True)

    seed_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    leech_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    download_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    last_updated = db.Column(db.DateTime(timezone=False))

    torrent = db.relationship('Torrent', uselist=False, back_populates='stats')


class Trackers(db.Model):
    __tablename__ = 'trackers'

    id = db.Column(db.Integer, primary_key=True)
    uri = db.Column(db.String(length=255, collation=COL_UTF8_GENERAL_CI),
                    nullable=False, unique=True)
    disabled = db.Column(db.Boolean, nullable=False, default=False)

    @classmethod
    def by_uri(cls, uri):
        return cls.query.filter_by(uri=uri).first()


class TorrentTrackers(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'torrent_trackers'

    torrent_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id', ondelete="CASCADE"), primary_key=True)
    tracker_id = db.Column(db.Integer, db.ForeignKey(
        'trackers.id', ondelete="CASCADE"), primary_key=True)
    order = db.Column(db.Integer, nullable=False, index=True)

    tracker = db.relationship('Trackers', uselist=False, lazy='joined')

    @classmethod
    def by_torrent_id(cls, torrent_id):
        return cls.query.filter_by(torrent_id=torrent_id).order_by(cls.order.desc())


class MainCategory(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'main_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(length=64), nullable=False)

    sub_categories = db.relationship('SubCategory', back_populates='main_category')
    torrents = db.relationship('Torrent', back_populates='main_category')

    def get_category_ids(self):
        return (self.id, 0)

    @property
    def id_as_string(self):
        return '_'.join(str(x) for x in self.get_category_ids())

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)


class SubCategory(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'sub_categories'

    id = db.Column(db.Integer, primary_key=True)
    main_category_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'main_categories.id'), primary_key=True)
    name = db.Column(db.String(length=64), nullable=False)

    main_category = db.relationship('MainCategory', uselist=False, back_populates='sub_categories')
#    torrents = db.relationship('Torrent', back_populates='sub_category'),
#        primaryjoin="and_(Torrent.sub_category_id == foreign(SubCategory.id), "
#                    "Torrent.main_category_id == SubCategory.main_category_id)")

    def get_category_ids(self):
        return (self.main_category_id, self.id)

    @property
    def id_as_string(self):
        return '_'.join(str(x) for x in self.get_category_ids())

    @classmethod
    def by_category_ids(cls, main_cat_id, sub_cat_id):
        return cls.query.get((sub_cat_id, main_cat_id))


class Comment(db.Model):
    __tablename__ = DB_TABLE_PREFIX + 'comments'

    id = db.Column(db.Integer, primary_key=True)
    torrent_id = db.Column(db.Integer, db.ForeignKey(
        DB_TABLE_PREFIX + 'torrents.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    text = db.Column(db.String(length=255), nullable=False)

    user = db.relationship('User', uselist=False, back_populates='comments', lazy="joined")

    def __repr__(self):
        return '<Comment %r>' % self.id

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()


class UserLevelType(IntEnum):
    REGULAR = 0
    TRUSTED = 1
    MODERATOR = 2
    SUPERADMIN = 3


class UserStatusType(Enum):
    INACTIVE = 0
    ACTIVE = 1
    BANNED = 2


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(length=32, collation=COL_ASCII_GENERAL_CI),
                         unique=True, nullable=False)
    email = db.Column(EmailType(length=255, collation=COL_ASCII_GENERAL_CI),
                      unique=True, nullable=True)
    password_hash = db.Column(PasswordType(max_length=255, schemes=['argon2']), nullable=False)
    status = db.Column(ChoiceType(UserStatusType, impl=db.Integer()), nullable=False)
    level = db.Column(ChoiceType(UserLevelType, impl=db.Integer()), nullable=False)

    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    last_login_date = db.Column(db.DateTime(timezone=False), default=None, nullable=True)
    last_login_ip = db.Column(db.Binary(length=16), default=None, nullable=True)

    torrents = db.relationship('Torrent', back_populates='user', lazy='dynamic')
    comments = db.relationship('Comment', back_populates='user', lazy='dynamic')
    # session = db.relationship('Session', uselist=False, back_populates='user')

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password_hash = password
        self.status = UserStatusType.INACTIVE
        self.level = UserLevelType.REGULAR

    def __repr__(self):
        return '<User %r>' % self.username

    def validate_authorization(self, password):
        ''' Returns a boolean for whether the user can be logged in '''
        checks = [
            # Password must match
            password == self.password_hash,
            # Reject inactive and banned users
            self.status == UserStatusType.ACTIVE
        ]
        return all(checks)

    def gravatar_url(self):
        # from http://en.gravatar.com/site/implement/images/python/
        size = 120
        # construct the url
        default_avatar = flask.url_for('static', filename='img/avatar/default.png', _external=True)
        gravatar_url = 'https://www.gravatar.com/avatar/{}?{}'.format(
            md5(self.email.encode('utf-8').lower()).hexdigest(),
            urlencode({'d': default_avatar, 's': str(size)}))
        return gravatar_url

    @property
    def userlevel_str(self):
        if self.level == UserLevelType.REGULAR:
            return 'User'
        elif self.level == UserLevelType.TRUSTED:
            return 'Trusted'
        elif self.level >= UserLevelType.MODERATOR:
            return 'Moderator'

    @property
    def ip_string(self):
        if self.last_login_ip:
            return str(ip_address(self.last_login_ip))

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def by_username(cls, username):
        user = cls.query.filter_by(username=username).first()
        return user

    @classmethod
    def by_email(cls, email):
        user = cls.query.filter_by(email=email).first()
        return user

    @classmethod
    def by_username_or_email(cls, username_or_email):
        return cls.by_username(username_or_email) or cls.by_email(username_or_email)

    @property
    def is_moderator(self):
        return self.level >= UserLevelType.MODERATOR

    @property
    def is_superadmin(self):
        return self.level == UserLevelType.SUPERADMIN

    @property
    def is_trusted(self):
        return self.level >= UserLevelType.TRUSTED


# class Session(db.Model):
#    __tablename__ = 'sessions'
#
#    session_id = db.Column(db.Integer, primary_key=True)
#    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#    login_ip = db.Column(db.Binary(length=16), nullable=True)
#    login_date = db.Column(db.DateTime(timezone=False), nullable=True)
#
#    user = db.relationship('User', back_populates='session')

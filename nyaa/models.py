import base64
import os.path
import re
from datetime import datetime
from enum import Enum, IntEnum
from hashlib import md5
from ipaddress import ip_address
from urllib.parse import unquote as unquote_url
from urllib.parse import urlencode

import flask
from markupsafe import escape as escape_markup

from sqlalchemy import ForeignKeyConstraint, Index, func
from sqlalchemy.ext import declarative
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy_fulltext import FullText
from sqlalchemy_utils import ChoiceType, EmailType, PasswordType

from nyaa.extensions import config, db
from nyaa.torrents import create_magnet

app = flask.current_app

if config['USE_MYSQL']:
    from sqlalchemy.dialects import mysql
    BinaryType = mysql.BINARY
    TextType = mysql.TEXT
    MediumBlobType = mysql.MEDIUMBLOB
    COL_UTF8_GENERAL_CI = 'utf8_general_ci'
    COL_UTF8MB4_BIN = 'utf8mb4_bin'
    COL_ASCII_GENERAL_CI = 'ascii_general_ci'
else:
    BinaryType = db.Binary
    TextType = db.String
    MediumBlobType = db.BLOB
    COL_UTF8_GENERAL_CI = 'NOCASE'
    COL_UTF8MB4_BIN = None
    COL_ASCII_GENERAL_CI = 'NOCASE'


# For property timestamps
UTC_EPOCH = datetime.utcfromtimestamp(0)


class DeclarativeHelperBase(object):
    ''' This class eases our nyaa-sukebei shenanigans by automatically adjusting
        __tablename__ and providing class methods for renaming references. '''
    # See http://docs.sqlalchemy.org/en/latest/orm/extensions/declarative/api.html

    __tablename_base__ = None
    __flavor__ = None

    @classmethod
    def _table_prefix_string(cls):
        return cls.__flavor__.lower() + '_'

    @classmethod
    def _table_prefix(cls, table_name):
        return cls._table_prefix_string() + table_name

    @classmethod
    def _flavor_prefix(cls, table_name):
        return cls.__flavor__ + table_name

    @declarative.declared_attr
    def __tablename__(cls):
        return cls._table_prefix(cls.__tablename_base__)


class FlagProperty(object):
    ''' This class will act as a wrapper between the given flag and the class's
        flag collection. '''

    def __init__(self, flag, flags_attr='flags'):
        self._flag = flag
        self._flags_attr_name = flags_attr

    def _get_flags(self, instance):
        return getattr(instance, self._flags_attr_name)

    def _set_flags(self, instance, value):
        return setattr(instance, self._flags_attr_name, value)

    def __get__(self, instance, owner_class):
        if instance is None:
            raise AttributeError()
        return bool(self._get_flags(instance) & self._flag)

    def __set__(self, instance, value):
        new_flags = (self._get_flags(instance) & ~self._flag) | (bool(value) and self._flag)
        self._set_flags(instance, new_flags)


class TorrentFlags(IntEnum):
    NONE = 0
    ANONYMOUS = 1
    HIDDEN = 2
    TRUSTED = 4
    REMAKE = 8
    COMPLETE = 16
    DELETED = 32
    BANNED = 64
    COMMENT_LOCKED = 128


class TorrentBase(DeclarativeHelperBase):
    __tablename_base__ = 'torrents'

    id = db.Column(db.Integer, primary_key=True)
    info_hash = db.Column(BinaryType(length=20), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(length=255, collation=COL_UTF8_GENERAL_CI),
                             nullable=False, index=True)
    torrent_name = db.Column(db.String(length=255), nullable=False)
    information = db.Column(db.String(length=255), nullable=False)
    description = db.Column(TextType(collation=COL_UTF8MB4_BIN), nullable=False)

    filesize = db.Column(db.BIGINT, default=0, nullable=False, index=True)
    encoding = db.Column(db.String(length=32), nullable=False)
    flags = db.Column(db.Integer, default=0, nullable=False, index=True)

    @declarative.declared_attr
    def uploader_id(cls):
        # Even though this is same for both tables, declarative requires this
        return db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    uploader_ip = db.Column(db.Binary(length=16), default=None, nullable=True)
    has_torrent = db.Column(db.Boolean, nullable=False, default=False)

    comment_count = db.Column(db.Integer, default=0, nullable=False, index=True)

    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    @declarative.declared_attr
    def main_category_id(cls):
        fk = db.ForeignKey(cls._table_prefix('main_categories.id'))
        return db.Column(db.Integer, fk, nullable=False)

    sub_category_id = db.Column(db.Integer, nullable=False)

    @declarative.declared_attr
    def redirect(cls):
        fk = db.ForeignKey(cls._table_prefix('torrents.id'))
        return db.Column(db.Integer, fk, nullable=True)

    @declarative.declared_attr
    def __table_args__(cls):
        return (
            Index(cls._table_prefix('uploader_flag_idx'), 'uploader_id', 'flags'),
            ForeignKeyConstraint(
                ['main_category_id', 'sub_category_id'],
                [cls._table_prefix('sub_categories.main_category_id'),
                 cls._table_prefix('sub_categories.id')]
            ), {}
        )

    @declarative.declared_attr
    def user(cls):
        return db.relationship('User', uselist=False, back_populates=cls._table_prefix('torrents'))

    @declarative.declared_attr
    def main_category(cls):
        return db.relationship(cls._flavor_prefix('MainCategory'), uselist=False,
                               back_populates='torrents', lazy="joined")

    @declarative.declared_attr
    def sub_category(cls):
        join_sql = ("and_({0}SubCategory.id == foreign({0}Torrent.sub_category_id), "
                    "{0}SubCategory.main_category_id == {0}Torrent.main_category_id)")
        return db.relationship(cls._flavor_prefix('SubCategory'), uselist=False,
                               backref='torrents', lazy="joined",
                               primaryjoin=join_sql.format(cls.__flavor__))

    @declarative.declared_attr
    def filelist(cls):
        return db.relationship(cls._flavor_prefix('TorrentFilelist'), uselist=False,
                               cascade="all, delete-orphan", back_populates='torrent')

    @declarative.declared_attr
    def stats(cls):
        return db.relationship(cls._flavor_prefix('Statistic'), uselist=False,
                               cascade="all, delete-orphan", back_populates='torrent',
                               lazy='joined')

    @declarative.declared_attr
    def trackers(cls):
        return db.relationship(cls._flavor_prefix('TorrentTrackers'), uselist=True,
                               cascade="all, delete-orphan",
                               order_by=cls._flavor_prefix('TorrentTrackers.order'))

    @declarative.declared_attr
    def comments(cls):
        return db.relationship(cls._flavor_prefix('Comment'), uselist=True,
                               cascade="all, delete-orphan")

    def __repr__(self):
        return '<{0} #{1.id} \'{1.display_name}\' {1.filesize}b>'.format(type(self).__name__, self)

    def update_comment_count(self):
        self.comment_count = db.session.query(func.count(
            Comment.id)).filter_by(torrent_id=self.id).first()[0]
        return self.comment_count

    @classmethod
    def update_comment_count_db(cls, torrent_id):
        cls.query.filter_by(id=torrent_id).update({'comment_count': db.session.query(
            func.count(Comment.id)).filter_by(torrent_id=torrent_id).as_scalar()}, False)

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
                return('<a rel="noopener noreferrer nofollow" '
                       'href="{0}">{1}</a>'.format(url, escape_markup(unquote_url(url))))
        # Escaped
        return escape_markup(self.information)

    @property
    def info_dict_path(self):
        ''' Returns a path to the info_dict file in form of 'info_dicts/aa/bb/aabbccddee...' '''
        info_hash = self.info_hash_as_hex
        return os.path.join(app.config['BASE_DIR'], 'info_dicts',
                            info_hash[0:2], info_hash[2:4], info_hash)

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

    # Flag properties below

    anonymous = FlagProperty(TorrentFlags.ANONYMOUS)
    hidden = FlagProperty(TorrentFlags.HIDDEN)
    deleted = FlagProperty(TorrentFlags.DELETED)
    banned = FlagProperty(TorrentFlags.BANNED)
    trusted = FlagProperty(TorrentFlags.TRUSTED)
    remake = FlagProperty(TorrentFlags.REMAKE)
    complete = FlagProperty(TorrentFlags.COMPLETE)
    comment_locked = FlagProperty(TorrentFlags.COMMENT_LOCKED)

    # Class methods

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def by_info_hash(cls, info_hash):
        return cls.query.filter_by(info_hash=info_hash).first()

    @classmethod
    def by_info_hash_hex(cls, info_hash_hex):
        info_hash_bytes = bytearray.fromhex(info_hash_hex)
        return cls.by_info_hash(info_hash_bytes)


class TorrentFilelistBase(DeclarativeHelperBase):
    __tablename_base__ = 'torrents_filelist'

    __table_args__ = {'mysql_row_format': 'COMPRESSED'}

    @declarative.declared_attr
    def torrent_id(cls):
        fk = db.ForeignKey(cls._table_prefix('torrents.id'), ondelete="CASCADE")
        return db.Column(db.Integer, fk, primary_key=True)

    filelist_blob = db.Column(MediumBlobType, nullable=True)

    @declarative.declared_attr
    def torrent(cls):
        return db.relationship(cls._flavor_prefix('Torrent'), uselist=False,
                               back_populates='filelist')


class StatisticBase(DeclarativeHelperBase):
    __tablename_base__ = 'statistics'

    @declarative.declared_attr
    def torrent_id(cls):
        fk = db.ForeignKey(cls._table_prefix('torrents.id'), ondelete="CASCADE")
        return db.Column(db.Integer, fk, primary_key=True)

    seed_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    leech_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    download_count = db.Column(db.Integer, default=0, nullable=False, index=True)
    last_updated = db.Column(db.DateTime(timezone=False))

    @declarative.declared_attr
    def torrent(cls):
        return db.relationship(cls._flavor_prefix('Torrent'), uselist=False,
                               back_populates='stats')


class Trackers(db.Model):
    __tablename__ = 'trackers'

    id = db.Column(db.Integer, primary_key=True)
    uri = db.Column(db.String(length=255, collation=COL_UTF8_GENERAL_CI),
                    nullable=False, unique=True)
    is_webseed = db.Column(db.Boolean, nullable=False, default=False)
    disabled = db.Column(db.Boolean, nullable=False, default=False)

    @classmethod
    def by_uri(cls, uri):
        return cls.query.filter_by(uri=uri).first()


class TorrentTrackersBase(DeclarativeHelperBase):
    __tablename_base__ = 'torrent_trackers'

    @declarative.declared_attr
    def torrent_id(cls):
        fk = db.ForeignKey(cls._table_prefix('torrents.id'), ondelete="CASCADE")
        return db.Column(db.Integer, fk, primary_key=True)

    @declarative.declared_attr
    def tracker_id(cls):
        fk = db.ForeignKey('trackers.id', ondelete="CASCADE")
        return db.Column(db.Integer, fk, primary_key=True)

    order = db.Column(db.Integer, nullable=False, index=True)

    @declarative.declared_attr
    def tracker(cls):
        return db.relationship('Trackers', uselist=False, lazy='joined')

    @classmethod
    def by_torrent_id(cls, torrent_id):
        return cls.query.filter_by(torrent_id=torrent_id).order_by(cls.order.desc())


class MainCategoryBase(DeclarativeHelperBase):
    __tablename_base__ = 'main_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(length=64), nullable=False)

    @declarative.declared_attr
    def sub_categories(cls):
        return db.relationship(cls._flavor_prefix('SubCategory'), back_populates='main_category')

    @declarative.declared_attr
    def torrents(cls):
        return db.relationship(cls._flavor_prefix('Torrent'), back_populates='main_category')

    def get_category_ids(self):
        return (self.id, 0)

    @property
    def id_as_string(self):
        return '_'.join(str(x) for x in self.get_category_ids())

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)


class SubCategoryBase(DeclarativeHelperBase):
    __tablename_base__ = 'sub_categories'

    id = db.Column(db.Integer, primary_key=True)

    @declarative.declared_attr
    def main_category_id(cls):
        fk = db.ForeignKey(cls._table_prefix('main_categories.id'))
        return db.Column(db.Integer, fk, primary_key=True)

    name = db.Column(db.String(length=64), nullable=False)

    @declarative.declared_attr
    def main_category(cls):
        return db.relationship(cls._flavor_prefix('MainCategory'), uselist=False,
                               back_populates='sub_categories')

    def get_category_ids(self):
        return (self.main_category_id, self.id)

    @property
    def id_as_string(self):
        return '_'.join(str(x) for x in self.get_category_ids())

    @classmethod
    def by_category_ids(cls, main_cat_id, sub_cat_id):
        return cls.query.get((sub_cat_id, main_cat_id))


class CommentBase(DeclarativeHelperBase):
    __tablename_base__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)

    @declarative.declared_attr
    def torrent_id(cls):
        return db.Column(db.Integer, db.ForeignKey(
            cls._table_prefix('torrents.id'), ondelete='CASCADE'), nullable=False)

    @declarative.declared_attr
    def user_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))

    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    edited_time = db.Column(db.DateTime(timezone=False), onupdate=datetime.utcnow)
    text = db.Column(TextType(collation=COL_UTF8MB4_BIN), nullable=False)

    @declarative.declared_attr
    def user(cls):
        return db.relationship('User', uselist=False,
                               back_populates=cls._table_prefix('comments'), lazy="joined")

    @declarative.declared_attr
    def torrent(cls):
        return db.relationship(cls._flavor_prefix('Torrent'), uselist=False,
                               back_populates='comments')

    def __repr__(self):
        return '<Comment %r>' % self.id

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @property
    def edited_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.edited_time - UTC_EPOCH).total_seconds() if self.edited_time else 0

    @property
    def editable_until(self):
        return self.created_utc_timestamp + config['EDITING_TIME_LIMIT']

    @property
    def editing_limit_exceeded(self):
        limit = config['EDITING_TIME_LIMIT']
        return bool(limit and (datetime.utcnow() - self.created_time).total_seconds() >= limit)


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
    registration_ip = db.Column(db.Binary(length=16), default=None, nullable=True)

    nyaa_torrents = db.relationship('NyaaTorrent', back_populates='user', lazy='dynamic')
    nyaa_comments = db.relationship('NyaaComment', back_populates='user', lazy='dynamic')

    sukebei_torrents = db.relationship('SukebeiTorrent', back_populates='user', lazy='dynamic')
    sukebei_comments = db.relationship('SukebeiComment', back_populates='user', lazy='dynamic')

    bans = db.relationship('Ban', uselist=True, foreign_keys='Ban.user_id')

    preferences = db.relationship('UserPreferences', back_populates='user', uselist=False)

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
        if 'DEFAULT_GRAVATAR_URL' in app.config:
            default_url = app.config['DEFAULT_GRAVATAR_URL']
        else:
            default_url = flask.url_for('static', filename='img/avatar/default.png',
                                        _external=True)
        if app.config['ENABLE_GRAVATAR']:
            # from http://en.gravatar.com/site/implement/images/python/
            params = {
                # Image size (https://en.gravatar.com/site/implement/images/#size)
                's': 120,
                # Default image (https://en.gravatar.com/site/implement/images/#default-image)
                'd': default_url,
                # Image rating (https://en.gravatar.com/site/implement/images/#rating)
                # Nyaa: PG-rated, Sukebei: X-rated
                'r': 'pg' if app.config['SITE_FLAVOR'] == 'nyaa' else 'x',
            }
            # construct the url
            return 'https://www.gravatar.com/avatar/{}?{}'.format(
                md5(self.email.encode('utf-8').lower()).hexdigest(), urlencode(params))
        else:
            return default_url

    @property
    def userlevel_str(self):
        level = ''
        if self.level == UserLevelType.REGULAR:
            level = 'User'
        elif self.level == UserLevelType.TRUSTED:
            level = 'Trusted'
        elif self.level == UserLevelType.MODERATOR:
            level = 'Moderator'
        elif self.level >= UserLevelType.SUPERADMIN:
            level = 'Administrator'
        if self.is_banned:
            level = 'BANNED ' + level
        return level

    @property
    def userstatus_str(self):
        if self.status == UserStatusType.INACTIVE:
            return 'Inactive'
        elif self.status == UserStatusType.ACTIVE:
            return 'Active'
        elif self.status == UserStatusType.BANNED:
            return 'Banned'

    @property
    def userlevel_color(self):
        color = ''
        if self.level == UserLevelType.REGULAR:
            color = 'default'
        elif self.level == UserLevelType.TRUSTED:
            color = 'success'
        elif self.level >= UserLevelType.MODERATOR:
            color = 'purple'
        if self.is_banned:
            color += ' strike'
        return color

    @property
    def ip_string(self):
        if self.last_login_ip:
            return str(ip_address(self.last_login_ip))

    @property
    def reg_ip_string(self):
        if self.registration_ip:
            return str(ip_address(self.registration_ip))

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def by_username(cls, username):
        def isascii(s): return len(s) == len(s.encode())
        if not isascii(username):
            return None

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

    @property
    def is_banned(self):
        return self.status == UserStatusType.BANNED

    @property
    def is_active(self):
        return self.status != UserStatusType.INACTIVE

    @property
    def age(self):
        '''Account age in seconds'''
        return (datetime.utcnow() - self.created_time).total_seconds()

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @property
    def satisfies_trusted_reqs(self):
        num_total = 0
        downloads_total = 0
        for ts_flavor, t_flavor in ((NyaaStatistic, NyaaTorrent),
                                    (SukebeiStatistic, SukebeiTorrent)):
            uploads = db.session.query(func.count(t_flavor.id)).\
                filter(t_flavor.user == self).\
                filter(t_flavor.flags.op('&')(int(TorrentFlags.REMAKE)).is_(False)).scalar()
            dls = db.session.query(func.sum(ts_flavor.download_count)).\
                join(t_flavor).\
                filter(t_flavor.user == self).\
                filter(t_flavor.flags.op('&')(int(TorrentFlags.REMAKE)).is_(False)).scalar()
            num_total += uploads or 0
            downloads_total += dls or 0
        return (num_total >= config['TRUSTED_MIN_UPLOADS'] and
                downloads_total >= config['TRUSTED_MIN_DOWNLOADS'])


class UserPreferences(db.Model):
    __tablename__ = 'user_preferences'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

    def __init__(self, user_id):
        self.user_id = user_id

    def __repr__(self):
        return '<UserPreferences %r>' % self.user_id

    user = db.relationship('User', back_populates='preferences')
    hide_comments = db.Column(db.Boolean, nullable=False, default=False)


class AdminLogBase(DeclarativeHelperBase):
    __tablename_base__ = 'adminlog'

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    log = db.Column(db.String(length=1024), nullable=False)

    @declarative.declared_attr
    def admin_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __init__(self, log, admin_id):
        self.log = log
        self.admin_id = admin_id

    def __repr__(self):
        return '<AdminLog %r>' % self.id

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @declarative.declared_attr
    def admin(cls):
        return db.relationship('User', uselist=False, lazy="joined")

    @classmethod
    def all_logs(cls):
        return cls.query


class ReportStatus(IntEnum):
    IN_REVIEW = 0
    VALID = 1
    INVALID = 2


class ReportBase(DeclarativeHelperBase):
    __tablename_base__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    reason = db.Column(db.String(length=255), nullable=False)
    status = db.Column(ChoiceType(ReportStatus, impl=db.Integer()), nullable=False)

    @declarative.declared_attr
    def torrent_id(cls):
        return db.Column(db.Integer, db.ForeignKey(
            cls._table_prefix('torrents.id'), ondelete='CASCADE'), nullable=False)

    @declarative.declared_attr
    def user_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id'))

    @declarative.declared_attr
    def user(cls):
        return db.relationship('User', uselist=False, lazy="joined")

    @declarative.declared_attr
    def torrent(cls):
        return db.relationship(cls._flavor_prefix('Torrent'), uselist=False, lazy="joined")

    def __init__(self, torrent_id, user_id, reason):
        self.torrent_id = torrent_id
        self.user_id = user_id
        self.reason = reason
        self.status = ReportStatus.IN_REVIEW

    def __repr__(self):
        return '<Report %r>' % self.id

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def not_reviewed(cls, page):
        reports = cls.query.filter_by(status=0).paginate(page=page, per_page=20)
        return reports

    @classmethod
    def remove_reviewed(cls, id):
        return cls.query.filter(cls.torrent_id == id, cls.status == 0).delete()


class Ban(db.Model):
    __tablename__ = 'bans'

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_ip = db.Column(db.Binary(length=16), nullable=True)
    reason = db.Column(db.String(length=2048), nullable=False)

    admin = db.relationship('User', uselist=False, lazy='joined', foreign_keys=[admin_id])
    user = db.relationship('User', uselist=False, lazy='joined', foreign_keys=[user_id])

    __table_args__ = (
        Index('user_ip_4', 'user_ip', mysql_length=4, unique=True),
        Index('user_ip_16', 'user_ip', mysql_length=16, unique=True),
    )

    def __repr__(self):
        return '<Ban %r>' % self.id

    @property
    def ip_string(self):
        if self.user_ip:
            return str(ip_address(self.user_ip))

    @classmethod
    def all_bans(cls):
        return cls.query

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)

    @classmethod
    def banned(cls, user_id, user_ip):
        if user_id:
            if user_ip:
                return cls.query.filter((cls.user_id == user_id) | (cls.user_ip == user_ip))
            return cls.query.filter(cls.user_id == user_id)
        if user_ip:
            return cls.query.filter(cls.user_ip == user_ip)
        return None


class TrackerApiBase(DeclarativeHelperBase):
    __tablename_base__ = 'trackerapi'

    id = db.Column(db.Integer, primary_key=True)
    info_hash = db.Column(BinaryType(length=20), nullable=False)
    method = db.Column(db.String(length=255), nullable=False)
    # Methods = insert, remove

    def __init__(self, info_hash, method):
        self.info_hash = info_hash
        self.method = method


class RangeBan(db.Model):
    __tablename__ = 'rangebans'

    id = db.Column(db.Integer, primary_key=True)
    _cidr_string = db.Column('cidr_string', db.String(length=18), nullable=False)
    masked_cidr = db.Column(db.BigInteger, nullable=False,
                            index=True)
    mask = db.Column(db.BigInteger, nullable=False, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    # If this rangeban may be automatically cleared once it becomes
    # out of date, set this column to the creation time of the ban.
    # None (or NULL in the db) is understood as the ban being permanent.
    temp = db.Column(db.DateTime(timezone=False), nullable=True, default=None)

    @property
    def cidr_string(self):
        return self._cidr_string

    @cidr_string.setter
    def cidr_string(self, s):
        subnet, masked_bits = s.split('/')
        subnet_b = ip_address(subnet).packed
        self.mask = (1 << 32) - (1 << (32 - int(masked_bits)))
        self.masked_cidr = int.from_bytes(subnet_b, 'big') & self.mask
        self._cidr_string = s

    @classmethod
    def is_rangebanned(cls, ip):
        if len(ip) > 4:
            raise NotImplementedError("IPv6 is unsupported.")
        elif len(ip) < 4:
            raise ValueError("Not an IP address.")
        ip_int = int.from_bytes(ip, 'big')
        q = cls.query.filter(cls.mask.op('&')(ip_int) == cls.masked_cidr,
                             cls.enabled)
        return q.count() > 0


class TrustedApplicationStatus(IntEnum):
    # If you change these, don't forget to change is_closed in TrustedApplication
    NEW = 0
    REVIEWED = 1
    ACCEPTED = 2
    REJECTED = 3


class TrustedApplication(db.Model):
    __tablename__ = 'trusted_applications'

    id = db.Column(db.Integer, primary_key=True)
    submitter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    closed_time = db.Column(db.DateTime(timezone=False))
    why_want = db.Column(db.String(length=4000), nullable=False)
    why_give = db.Column(db.String(length=4000), nullable=False)
    status = db.Column(ChoiceType(TrustedApplicationStatus, impl=db.Integer()), nullable=False,
                       default=TrustedApplicationStatus.NEW)
    reviews = db.relationship('TrustedReview', backref='trusted_applications')
    submitter = db.relationship('User', uselist=False, lazy='joined', foreign_keys=[submitter_id])

    @hybrid_property
    def is_closed(self):
        # We can't use the attribute names from TrustedApplicationStatus in an or here because of
        # SQLAlchemy jank. It'll generate the wrong query.
        return self.status > 1

    @hybrid_property
    def is_new(self):
        return self.status == TrustedApplicationStatus.NEW

    @hybrid_property
    def is_reviewed(self):
        return self.status == TrustedApplicationStatus.REVIEWED

    @hybrid_property
    def is_rejected(self):
        return self.status == TrustedApplicationStatus.REJECTED

    @property
    def created_utc_timestamp(self):
        ''' Returns a UTC POSIX timestamp, as seconds '''
        return (self.created_time - UTC_EPOCH).total_seconds()

    @classmethod
    def by_id(cls, id):
        return cls.query.get(id)


class TrustedRecommendation(IntEnum):
    ACCEPT = 0
    REJECT = 1
    ABSTAIN = 2


class TrustedReview(db.Model):
    __tablename__ = 'trusted_reviews'

    id = db.Column(db.Integer, primary_key=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    app_id = db.Column(db.Integer, db.ForeignKey('trusted_applications.id'), nullable=False)
    created_time = db.Column(db.DateTime(timezone=False), default=datetime.utcnow)
    comment = db.Column(db.String(length=4000), nullable=False)
    recommendation = db.Column(ChoiceType(TrustedRecommendation, impl=db.Integer()),
                               nullable=False)
    reviewer = db.relationship('User', uselist=False, lazy='joined', foreign_keys=[reviewer_id])
    application = db.relationship('TrustedApplication', uselist=False, lazy='joined',
                                  foreign_keys=[app_id])


# Actually declare our site-specific classes

# Torrent
class NyaaTorrent(TorrentBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiTorrent(TorrentBase, db.Model):
    __flavor__ = 'Sukebei'


# Fulltext models for MySQL
if config['USE_MYSQL']:
    class NyaaTorrentNameSearch(FullText, NyaaTorrent):
        __fulltext_columns__ = ('display_name',)
        __table_args__ = {'extend_existing': True}

    class SukebeiTorrentNameSearch(FullText, SukebeiTorrent):
        __fulltext_columns__ = ('display_name',)
        __table_args__ = {'extend_existing': True}
else:
    # Bogus classes for Sqlite
    class NyaaTorrentNameSearch(object):
        pass

    class SukebeiTorrentNameSearch(object):
        pass


# TorrentFilelist
class NyaaTorrentFilelist(TorrentFilelistBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiTorrentFilelist(TorrentFilelistBase, db.Model):
    __flavor__ = 'Sukebei'


# Statistic
class NyaaStatistic(StatisticBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiStatistic(StatisticBase, db.Model):
    __flavor__ = 'Sukebei'


# TorrentTrackers
class NyaaTorrentTrackers(TorrentTrackersBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiTorrentTrackers(TorrentTrackersBase, db.Model):
    __flavor__ = 'Sukebei'


# MainCategory
class NyaaMainCategory(MainCategoryBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiMainCategory(MainCategoryBase, db.Model):
    __flavor__ = 'Sukebei'


# SubCategory
class NyaaSubCategory(SubCategoryBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiSubCategory(SubCategoryBase, db.Model):
    __flavor__ = 'Sukebei'


# Comment
class NyaaComment(CommentBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiComment(CommentBase, db.Model):
    __flavor__ = 'Sukebei'


# AdminLog
class NyaaAdminLog(AdminLogBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiAdminLog(AdminLogBase, db.Model):
    __flavor__ = 'Sukebei'


# Report
class NyaaReport(ReportBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiReport(ReportBase, db.Model):
    __flavor__ = 'Sukebei'


# TrackerApi
class NyaaTrackerApi(TrackerApiBase, db.Model):
    __flavor__ = 'Nyaa'


class SukebeiTrackerApi(TrackerApiBase, db.Model):
    __flavor__ = 'Sukebei'


# Choose our defaults for models.Torrent etc
if config['SITE_FLAVOR'] == 'nyaa':
    Torrent = NyaaTorrent
    TorrentFilelist = NyaaTorrentFilelist
    Statistic = NyaaStatistic
    TorrentTrackers = NyaaTorrentTrackers
    MainCategory = NyaaMainCategory
    SubCategory = NyaaSubCategory
    Comment = NyaaComment
    AdminLog = NyaaAdminLog
    Report = NyaaReport
    TorrentNameSearch = NyaaTorrentNameSearch
    TrackerApi = NyaaTrackerApi

elif config['SITE_FLAVOR'] == 'sukebei':
    Torrent = SukebeiTorrent
    TorrentFilelist = SukebeiTorrentFilelist
    Statistic = SukebeiStatistic
    TorrentTrackers = SukebeiTorrentTrackers
    MainCategory = SukebeiMainCategory
    SubCategory = SukebeiSubCategory
    Comment = SukebeiComment
    AdminLog = SukebeiAdminLog
    Report = SukebeiReport
    TorrentNameSearch = SukebeiTorrentNameSearch
    TrackerApi = SukebeiTrackerApi

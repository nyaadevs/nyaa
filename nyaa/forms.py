from nyaa import db, app
from nyaa.models import User
from nyaa import bencode, utils, models

import os
import re
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import TextField, PasswordField, BooleanField, TextAreaField, SelectField
from wtforms.validators import Required, Optional, Email, Length, EqualTo, ValidationError, Regexp

# For DisabledSelectField
from wtforms.widgets import Select as SelectWidget
from wtforms.widgets import html_params, HTMLString

from flask_wtf.recaptcha import RecaptchaField


class Unique(object):

    """ validator that checks field uniqueness """

    def __init__(self, model, field, message=None):
        self.model = model
        self.field = field
        if not message:
            message = 'This element already exists'
        self.message = message

    def __call__(self, form, field):
        check = self.model.query.filter(self.field == field.data).first()
        if check:
            raise ValidationError(self.message)


_username_validator = Regexp(
    r'[a-zA-Z0-9_\-]+',
    message='Your username must only consist of alphanumerics and _- (a-zA-Z0-9_-)')


class LoginForm(FlaskForm):
    username = TextField('Username or email address', [Required(), _username_validator])
    password = PasswordField('Password', [Required()])


class RegisterForm(FlaskForm):
    username = TextField('Username', [
        Required(),
        Length(min=3, max=32),
        _username_validator,
        Unique(User, User.username, 'Username not availiable')
    ])

    email = TextField('Email address', [
        Email(),
        Required(),
        Length(min=5, max=128),
        Unique(User, User.email, 'Email already in use by another account')
    ])

    password = PasswordField('Password', [
        Required(),
        EqualTo('password_confirm', message='Passwords must match'),
        Length(min=6, max=1024,
               message='Password must be at least %(min)d characters long.')
    ])

    password_confirm = PasswordField('Password (confirm)')

    if app.config['USE_RECAPTCHA']:
        recaptcha = RecaptchaField()


class ProfileForm(FlaskForm):
    email = TextField('New email address', [
        Email(),
        Optional(),
        Length(min=5, max=128),
        Unique(User, User.email, 'Email is taken')
    ])

    current_password = PasswordField('Current password', [Optional()])

    new_password = PasswordField('New password (confirm)', [
        Optional(),
        EqualTo('password_confirm', message='Passwords must match'),
        Length(min=6, max=1024,
               message='Password must be at least %(min)d characters long.')
    ])

    password_confirm = PasswordField('Repeat Password')


# Classes for a SelectField that can be set to disable options (id, name, disabled)
# TODO: Move to another file for cleaner look
class DisabledSelectWidget(SelectWidget):
    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        if self.multiple:
            kwargs['multiple'] = True
        html = ['<select %s>' % html_params(name=field.name, **kwargs)]
        for val, label, selected, disabled in field.iter_choices():
            extra = disabled and {'disabled': ''} or {}
            html.append(self.render_option(val, label, selected, **extra))
        html.append('</select>')
        return HTMLString(''.join(html))


class DisabledSelectField(SelectField):
    widget = DisabledSelectWidget()

    def iter_choices(self):
        for choice_tuple in self.choices:
            value, label = choice_tuple[:2]
            disabled = len(choice_tuple) == 3 and choice_tuple[2] or False
            yield (value, label, self.coerce(value) == self.data, disabled)

    def pre_validate(self, form):
        for v in self.choices:
            if self.data == v[0]:
                break
        else:
            raise ValueError(self.gettext('Not a valid choice'))


class CommentForm(FlaskForm):
    comment = TextAreaField('Make a comment', [
        Length(max=255, message='Comment must be at most %(max)d characters long.'),
        Required()
    ])


class EditForm(FlaskForm):
    display_name = TextField('Display name', [
        Length(min=3, max=255,
               message='Torrent name must be at least %(min)d characters and %(max)d at most.')
    ])

    category = DisabledSelectField('Category')

    def validate_category(form, field):
        cat_match = re.match(r'^(\d+)_(\d+)$', field.data)
        if not cat_match:
            raise ValidationError('You must select a category')

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        cat = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)

        if not cat:
            raise ValidationError('You must select a proper category')

        field.parsed_data = cat

    is_hidden = BooleanField('Hidden')
    is_deleted = BooleanField('Deleted')
    is_remake = BooleanField('Remake')
    is_anonymous = BooleanField('Anonymous')
    is_complete = BooleanField('Complete')

    information = TextField('Information', [
        Length(max=255, message='Information must be at most %(max)d characters long.')
    ])
    description = TextAreaField('Description (markdown supported)', [
        Length(max=10 * 1024, message='Description must be at most %(max)d characters long.')
    ])


class UploadForm(FlaskForm):

    class Meta:
        csrf = False

    torrent_file = FileField('Torrent file', [
        FileRequired()
    ])

    display_name = TextField('Display name (optional)', [
        Optional(),
        Length(min=3, max=255,
               message='Torrent name must be at least %(min)d characters long and %(max)d at most.')
    ])

    # category = SelectField('Category')
    category = DisabledSelectField('Category')

    def validate_category(form, field):
        cat_match = re.match(r'^(\d+)_(\d+)$', field.data)
        if not cat_match:
            raise ValidationError('You must select a category')

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        cat = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)

        if not cat:
            raise ValidationError('You must select a proper category')

        field.parsed_data = cat

    is_hidden = BooleanField('Hidden')
    is_remake = BooleanField('Remake')
    is_anonymous = BooleanField('Anonymous')
    is_complete = BooleanField('Complete')

    information = TextField('Information', [
        Length(max=255, message='Information must be at most %(max)d characters long.')
    ])
    description = TextAreaField('Description (markdown supported)', [
        Length(max=10 * 1024, message='Description must be at most %(max)d characters long.')
    ])

    def validate_torrent_file(form, field):
        # Decode and ensure data is bencoded data
        try:
            torrent_dict = bencode.decode(field.data)
            # field.data.close()
        except (bencode.MalformedBencodeException, UnicodeError):
            raise ValidationError('Malformed torrent file')

        # Uncomment for debug print of the torrent
        # _debug_print_torrent_metadata(torrent_dict)

        try:
            _validate_torrent_metadata(torrent_dict)
        except AssertionError as e:
            raise ValidationError('Malformed torrent metadata ({})'.format(e.args[0]))

        try:
            _validate_trackers(torrent_dict)
        except AssertionError as e:
            raise ValidationError('Malformed torrent trackers ({})'.format(e.args[0]))

        if app.config.get('ENFORCE_MAIN_ANNOUNCE_URL'):
            main_announce_url = app.config.get('MAIN_ANNOUNCE_URL')
            if not main_announce_url:
                raise Exception('Config MAIN_ANNOUNCE_URL not set!')

            announce = torrent_dict.get('announce', b'').decode('utf-8')
            if announce != main_announce_url:
                raise ValidationError('Please set {} as the first tracker in the torrent'.format(main_announce_url))

        # Note! bencode will sort dict keys, as per the spec
        # This may result in a different hash if the uploaded torrent does not match the
        # spec, but it's their own fault for using broken software! Right?
        bencoded_info_dict = bencode.encode(torrent_dict['info'])
        info_hash = utils.sha1_hash(bencoded_info_dict)

        # Check if the info_hash exists already in the database
        existing_torrent = models.Torrent.by_info_hash(info_hash)
        if existing_torrent:
            raise ValidationError('That torrent already exists (#{})'.format(existing_torrent.id))

        # Torrent is legit, pass original filename and dict along
        field.parsed_data = TorrentFileData(filename=os.path.basename(field.data.filename),
                                            torrent_dict=torrent_dict,
                                            info_hash=info_hash,
                                            bencoded_info_dict=bencoded_info_dict)


class TorrentFileData(object):
    """Quick and dirty class to pass data from the validator"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# https://wiki.theory.org/BitTorrentSpecification#Metainfo_File_Structure


def _validate_trackers(torrent_dict):
    announce = torrent_dict.get('announce')
    _validate_bytes(announce)

    announce_list = torrent_dict.get('announce-list')
    if announce_list is not None:
        _validate_list(announce_list, 'announce-list')

        for announce in announce_list:
            _validate_list(announce, 'announce-list item')

            _validate_bytes(announce[0], 'announce-list item item')


def _validate_torrent_metadata(torrent_dict):
    ''' Validates a torrent metadata dict, raising AssertionError on errors '''
    assert isinstance(torrent_dict, dict), 'torrent metadata is not a dict'

    info_dict = torrent_dict.get('info')
    assert info_dict is not None, 'no info_dict in torrent'
    assert isinstance(info_dict, dict), 'info is not a dict'

    encoding_bytes = torrent_dict.get('encoding', b'utf-8')
    encoding = _validate_bytes(encoding_bytes, 'encoding', 'utf-8').lower()

    name = info_dict.get('name')
    _validate_bytes(name, 'name', test_decode=encoding)

    piece_length = info_dict.get('piece length')
    _validate_number(piece_length, 'piece length', check_positive=True)

    pieces = info_dict.get('pieces')
    _validate_bytes(pieces, 'pieces')
    assert len(pieces) % 20 == 0, 'pieces length is not a multiple of 20'

    files = info_dict.get('files')
    if files is not None:
        _validate_list(files, 'filelist')

        for file_dict in files:
            file_length = file_dict.get('length')
            _validate_number(file_length, 'file length', check_positive_or_zero=True)

            path_list = file_dict.get('path')
            _validate_list(path_list, 'path')
            for path_part in path_list:
                _validate_bytes(path_part, 'path part', test_decode=encoding)

    else:
        length = info_dict.get('length')
        _validate_number(length, 'length', check_positive=True)


def _validate_bytes(value, name='value', test_decode=None):
    assert isinstance(value, bytes), name + ' is not bytes'
    assert len(value) > 0, name + ' is empty'
    if test_decode:
        try:
            return value.decode(test_decode)
        except UnicodeError:
            raise AssertionError(name + ' could not be decoded from ' + repr(test_decode))


def _validate_number(value, name='value', check_positive=False, check_positive_or_zero=False):
    assert isinstance(value, int), name + ' is not an int'
    if check_positive_or_zero:
        assert value >= 0, name + ' is less than 0'
    elif check_positive:
        assert value > 0, name + ' is not positive'


def _validate_list(value, name='value', check_empty=False):
    assert isinstance(value, list), name + ' is not a list'
    if check_empty:
        assert len(value) > 0, name + ' is empty'


def _debug_print_torrent_metadata(torrent_dict):
    from pprint import pprint

    # Temporarily remove 'pieces' from infodict for clean debug prints
    info_dict = torrent_dict.get('info', {})
    orig_pieces = info_dict.get('pieces')

    info_dict['pieces'] = '<piece data>'
    pprint(torrent_dict)

    info_dict['pieces'] = orig_pieces

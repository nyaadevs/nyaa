import functools
import os
import re

import flask
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from flask_wtf.recaptcha import RecaptchaField
from flask_wtf.recaptcha.validators import Recaptcha as RecaptchaValidator
from wtforms import (BooleanField, HiddenField, PasswordField, SelectField, StringField,
                     SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length, Optional, Regexp,
                                StopValidation, ValidationError)
from wtforms.widgets import HTMLString  # For DisabledSelectField
from wtforms.widgets import Select as SelectWidget  # For DisabledSelectField
from wtforms.widgets import html_params

import dns.exception
import dns.resolver

from nyaa import bencode, models, utils
from nyaa.extensions import config
from nyaa.models import User

app = flask.current_app


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


def stop_on_validation_error(f):
    ''' A decorator which will turn raised ValidationErrors into StopValidations '''
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            # Replace the error with a StopValidation to stop the validation chain
            raise StopValidation(*e.args) from e
    return decorator


def recaptcha_validator_shim(form, field):
    if app.config['USE_RECAPTCHA']:
        return RecaptchaValidator()(form, field)
    else:
        # Always pass validating the recaptcha field if disabled
        return True


def upload_recaptcha_validator_shim(form, field):
    ''' Selectively does a recaptcha validation '''
    if app.config['USE_RECAPTCHA']:
        # Recaptcha anonymous and new users
        if not flask.g.user or flask.g.user.age < app.config['ACCOUNT_RECAPTCHA_AGE']:
            return RecaptchaValidator()(form, field)
    else:
        # Always pass validating the recaptcha field if disabled
        return True


def register_email_blacklist_validator(form, field):
    email_blacklist = app.config.get('EMAIL_BLACKLIST', [])
    email = field.data.strip()
    validation_exception = StopValidation('Blacklisted email provider')

    for item in email_blacklist:
        if isinstance(item, re.Pattern):
            if item.search(email):
                raise validation_exception
        elif isinstance(item, str):
            if item in email.lower():
                raise validation_exception
        else:
            raise Exception('Unexpected email validator type {!r} ({!r})'.format(type(item), item))
    return True


def register_email_server_validator(form, field):
    server_blacklist = app.config.get('EMAIL_SERVER_BLACKLIST', [])
    if not server_blacklist:
        return True

    validation_exception = StopValidation('Blacklisted email provider')
    email = field.data.strip()
    email_domain = email.split('@', 1)[-1]

    try:
        # Query domain MX records
        mx_records = list(dns.resolver.query(email_domain, 'MX'))

    except dns.exception.DNSException:
        app.logger.error('Unable to query MX records for email: %s - ignoring',
                         email, exc_info=False)
        return True

    for mx_record in mx_records:
        try:
            # Query mailserver A records
            a_records = list(dns.resolver.query(mx_record.exchange))
            for a_record in a_records:
                # Check for address in blacklist
                if a_record.address in server_blacklist:
                    app.logger.warning('Rejected email %s due to blacklisted mailserver (%s, %s)',
                                       email, a_record.address, mx_record.exchange)
                    raise validation_exception

        except dns.exception.DNSException:
            app.logger.warning('Failed to query A records for mailserver: %s (%s) - ignoring',
                               mx_record.exchange, email, exc_info=False)

    return True


_username_validator = Regexp(
    r'^[a-zA-Z0-9_\-]+$',
    message='Your username must only consist of alphanumerics and _- (a-zA-Z0-9_-)')


class LoginForm(FlaskForm):
    username = StringField('Username or email address', [DataRequired()])
    password = PasswordField('Password', [DataRequired()])


class PasswordResetRequestForm(FlaskForm):
    email = StringField('Email address', [
        Email(),
        DataRequired(),
        Length(min=5, max=128)
    ])

    recaptcha = RecaptchaField(validators=[recaptcha_validator_shim])


class PasswordResetForm(FlaskForm):
    password = PasswordField('Password', [
        DataRequired(),
        EqualTo('password_confirm', message='Passwords must match'),
        Length(min=6, max=1024,
               message='Password must be at least %(min)d characters long.')
    ])

    password_confirm = PasswordField('Password (confirm)')


class RegisterForm(FlaskForm):
    username = StringField('Username', [
        DataRequired(),
        Length(min=3, max=32),
        stop_on_validation_error(_username_validator),
        Unique(User, User.username, 'Username not available')
    ])

    email = StringField('Email address', [
        Email(),
        DataRequired(),
        Length(min=5, max=128),
        register_email_blacklist_validator,
        Unique(User, User.email, 'Email already in use by another account'),
        register_email_server_validator
    ])

    password = PasswordField('Password', [
        DataRequired(),
        EqualTo('password_confirm', message='Passwords must match'),
        Length(min=6, max=1024,
               message='Password must be at least %(min)d characters long.')
    ])

    password_confirm = PasswordField('Password (confirm)')

    if config['USE_RECAPTCHA']:
        recaptcha = RecaptchaField()


class ProfileForm(FlaskForm):
    email = StringField('New Email Address', [
        Email(),
        Optional(),
        Length(min=5, max=128),
        Unique(User, User.email, 'This email address has been taken')
    ])

    current_password = PasswordField('Current Password', [DataRequired()])

    new_password = PasswordField('New Password', [
        Optional(),
        EqualTo('password_confirm', message='Two passwords must match'),
        Length(min=6, max=1024,
               message='Password must be at least %(min)d characters long.')
    ])

    password_confirm = PasswordField('Repeat New Password')
    hide_comments = BooleanField('Hide comments by default')

    authorized_submit = SubmitField('Update')
    submit_settings = SubmitField('Update')


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
        Length(min=3, max=2048, message='Comment must be at least %(min)d characters '
               'long and %(max)d at most.'),
        DataRequired(message='Comment must not be empty.')
    ])

    recaptcha = RecaptchaField(validators=[upload_recaptcha_validator_shim])


class InlineButtonWidget(object):
    """
    Render a basic ``<button>`` field.
    """
    input_type = 'submit'
    html_params = staticmethod(html_params)

    def __call__(self, field, label=None, **kwargs):
        kwargs.setdefault('id', field.id)
        kwargs.setdefault('type', self.input_type)
        if not label:
            label = field.label.text
        return HTMLString('<button %s>' % self.html_params(name=field.name, **kwargs) + label)


class StringSubmitField(StringField):
    """
    Represents an ``<button type="submit">``.  This allows checking if a given
    submit button has been pressed.
    """
    widget = InlineButtonWidget()


class StringSubmitForm(FlaskForm):
    submit = StringSubmitField('Submit')


class EditForm(FlaskForm):
    display_name = StringField('Torrent display name', [
        Length(min=3, max=255, message='Torrent display name must be at least %(min)d characters '
               'long and %(max)d at most.')
    ])

    category = DisabledSelectField('Category')

    def validate_category(form, field):
        cat_match = re.match(r'^(\d+)_(\d+)$', field.data)
        if not cat_match:
            raise ValidationError('Please select a category')

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        cat = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)

        if not cat:
            raise ValidationError('Please select a proper category')

        field.parsed_data = cat

    is_hidden = BooleanField('Hidden')
    is_remake = BooleanField('Remake')
    is_anonymous = BooleanField('Anonymous')
    is_complete = BooleanField('Complete')
    is_trusted = BooleanField('Trusted')
    is_comment_locked = BooleanField('Lock Comments')

    information = StringField('Information', [
        Length(max=255, message='Information must be at most %(max)d characters long.')
    ])
    description = TextAreaField('Description', [
        Length(max=10 * 1024, message='Description must be at most %(max)d characters long.')
    ])

    submit = SubmitField('Save Changes')


class DeleteForm(FlaskForm):
    delete = SubmitField("Delete")
    ban = SubmitField("Delete & Ban")
    undelete = SubmitField("Undelete")
    unban = SubmitField("Unban")


class BanForm(FlaskForm):
    ban_user = SubmitField("Delete & Ban and Ban User")
    ban_userip = SubmitField("Delete & Ban and Ban User+IP")
    unban = SubmitField("Unban")

    _validator = DataRequired()

    def _validate_reason(form, field):
        if form.ban_user.data or form.ban_userip.data:
            return BanForm._validator(form, field)

    reason = TextAreaField('Ban Reason', [
        _validate_reason,
        Length(max=1024, message='Reason must be at most %(max)d characters long.')
    ])


class NukeForm(FlaskForm):
    nuke_torrents = SubmitField("\U0001F4A3 Nuke Torrents")
    nuke_comments = SubmitField("\U0001F4A3 Nuke Comments")


class UploadForm(FlaskForm):
    torrent_file = FileField('Torrent file', [
        FileRequired()
    ])

    display_name = StringField('Torrent display name (optional)', [
        Optional(),
        Length(min=3, max=255,
               message='Torrent display name must be at least %(min)d characters long and '
                       '%(max)d at most.')
    ])

    recaptcha = RecaptchaField(validators=[upload_recaptcha_validator_shim])

    category = DisabledSelectField('Category')

    def validate_category(form, field):
        cat_match = re.match(r'^(\d+)_(\d+)$', field.data)
        if not cat_match:
            raise ValidationError('Please select a category')

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        cat = models.SubCategory.by_category_ids(main_cat_id, sub_cat_id)

        if not cat:
            raise ValidationError('Please select a proper category')

        field.parsed_data = cat

    is_hidden = BooleanField('Hidden')
    is_remake = BooleanField('Remake')
    is_anonymous = BooleanField('Anonymous')
    is_complete = BooleanField('Complete')
    is_trusted = BooleanField('Trusted')
    is_comment_locked = BooleanField('Lock Comments')

    information = StringField('Information', [
        Length(max=255, message='Information must be at most %(max)d characters long.')
    ])
    description = TextAreaField('Description', [
        Length(max=10 * 1024, message='Description must be at most %(max)d characters long.')
    ])

    ratelimit = HiddenField()
    rangebanned = HiddenField()

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

        site_tracker = app.config.get('MAIN_ANNOUNCE_URL')
        ensure_tracker = app.config.get('ENFORCE_MAIN_ANNOUNCE_URL')

        try:
            tracker_found = _validate_trackers(torrent_dict, site_tracker)
        except AssertionError as e:
            raise ValidationError('Malformed torrent trackers ({})'.format(e.args[0]))

        # Ensure private torrents are using our tracker
        if torrent_dict['info'].get('private') == 1:
            if torrent_dict['announce'].decode('utf-8') != site_tracker:
                raise ValidationError(
                    'Private torrent: please set {} as the main tracker'.format(site_tracker))

        elif ensure_tracker and not tracker_found:
            raise ValidationError(
                'Please include {} in the trackers of the torrent'.format(site_tracker))

        # Note! bencode will sort dict keys, as per the spec
        # This may result in a different hash if the uploaded torrent does not match the
        # spec, but it's their own fault for using broken software! Right?
        bencoded_info_dict = bencode.encode(torrent_dict['info'])
        info_hash = utils.sha1_hash(bencoded_info_dict)

        # Check if the info_hash exists already in the database
        existing_torrent = models.Torrent.by_info_hash(info_hash)
        existing_torrent_id = existing_torrent.id if existing_torrent else None
        if existing_torrent and not existing_torrent.deleted:
            raise ValidationError('This torrent already exists (#{})'.format(existing_torrent.id))
        if existing_torrent and existing_torrent.banned:
            raise ValidationError('This torrent is banned'.format(existing_torrent.id))

        # Torrent is legit, pass original filename and dict along
        field.parsed_data = TorrentFileData(filename=os.path.basename(field.data.filename),
                                            torrent_dict=torrent_dict,
                                            info_hash=info_hash,
                                            bencoded_info_dict=bencoded_info_dict,
                                            db_id=existing_torrent_id)


class UserForm(FlaskForm):
    user_class = SelectField('Change User Class')
    activate_user = SubmitField('Activate User')

    def validate_user_class(form, field):
        if not field.data:
            raise ValidationError('Please select a proper user class')


class TorrentFileData(object):
    """Quick and dirty class to pass data from the validator"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# https://wiki.theory.org/BitTorrentSpecification#Metainfo_File_Structure


class ReportForm(FlaskForm):
    reason = TextAreaField('Report reason', [
        Length(min=3, max=255,
               message='Report reason must be at least %(min)d characters long '
                       'and %(max)d at most.'),
        DataRequired('You must provide a valid report reason.')
    ])


class ReportActionForm(FlaskForm):
    action = SelectField(choices=[('close', 'Close'), ('hide', 'Hide'), ('delete', 'Delete')])
    torrent = HiddenField()
    report = HiddenField()


class TrustedForm(FlaskForm):
    why_give_trusted = TextAreaField('Why do you think you should be given trusted status?', [
        Length(min=32, max=4000,
               message='Please explain why you think you should be given trusted status in at '
                       'least %(min)d but less than %(max)d characters.'),
        DataRequired('Please fill out all of the fields in the form.')
    ])
    why_want_trusted = TextAreaField('Why do you want to become a trusted user?', [
        Length(min=32, max=4000,
               message='Please explain why you want to become a trusted user in at least %(min)d '
                       'but less than %(max)d characters.'),
        DataRequired('Please fill out all of the fields in the form.')
    ])


class TrustedReviewForm(FlaskForm):
    comment = TextAreaField('Comment',
                            [Length(min=8, max=4000, message='Please provide a comment')])
    recommendation = SelectField(choices=[('abstain', 'Abstain'), ('reject', 'Reject'),
                                          ('accept', 'Accept')])


class TrustedDecisionForm(FlaskForm):
    accept = SubmitField('Accept')
    reject = SubmitField('Reject')


def _validate_trackers(torrent_dict, tracker_to_check_for=None):
    announce = torrent_dict.get('announce')
    assert announce is not None, 'no tracker in torrent'
    announce_string = _validate_bytes(announce, 'announce', test_decode='utf-8')

    tracker_found = tracker_to_check_for and (
        announce_string.lower() == tracker_to_check_for.lower()) or False

    announce_list = torrent_dict.get('announce-list')
    if announce_list is not None:
        _validate_list(announce_list, 'announce-list')

        for announce in announce_list:
            _validate_list(announce, 'announce-list item')

            announce_string = _validate_bytes(
                announce[0], 'announce-list item url', test_decode='utf-8')
            if tracker_to_check_for and announce_string.lower() == tracker_to_check_for.lower():
                tracker_found = True

    return tracker_found


# http://www.bittorrent.org/beps/bep_0019.html
def _validate_webseeds(torrent_dict):
    webseed_list = torrent_dict.get('url-list')
    if isinstance(webseed_list, bytes):
        # url-list should be omitted in case of no webseeds. However.
        # qBittorrent has an empty bytestring for no webseeds,
        # a bytestring for one and a list for multiple, so:
        # In case of a empty, keep as-is for next if.
        # In case of one, wrap it in a list.
        webseed_list = webseed_list and [webseed_list]

    # Merely check for truthiness ([], '' or a list with items)
    if webseed_list:
        _validate_list(webseed_list, 'url-list')

        for webseed_url in webseed_list:
            _validate_bytes(webseed_url, 'url-list item', test_decode='utf-8')


def _validate_torrent_metadata(torrent_dict):
    ''' Validates a torrent metadata dict, raising AssertionError on errors '''
    assert isinstance(torrent_dict, dict), 'torrent metadata is not a dict'

    info_dict = torrent_dict.get('info')
    assert info_dict is not None, 'no info_dict in torrent'
    assert isinstance(info_dict, dict), 'info is not a dict'

    encoding_bytes = torrent_dict.get('encoding', b'utf-8')
    encoding = _validate_bytes(encoding_bytes, 'encoding', test_decode='utf-8').lower()

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
            # Validate possible directory names
            for path_part in path_list[:-1]:
                _validate_bytes(path_part, 'path part', test_decode=encoding)
            # Validate actual filename, allow b'' to specify an empty directory
            _validate_bytes(path_list[-1], 'filename', check_empty=False, test_decode=encoding)

    else:
        length = info_dict.get('length')
        _validate_number(length, 'length', check_positive=True)

    _validate_webseeds(torrent_dict)


def _validate_bytes(value, name='value', check_empty=True, test_decode=None):
    assert isinstance(value, bytes), name + ' is not bytes'
    if check_empty:
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

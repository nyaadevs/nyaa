import flask
from werkzeug.datastructures import ImmutableMultiDict, CombinedMultiDict

from nyaa import app, db
from nyaa import models, forms
from nyaa import bencode, backend, utils
from nyaa import torrents

import json
import os.path
#from orderedset import OrderedSet
#from werkzeug import secure_filename

# #################################### API HELPERS ####################################


def validate_user(upload_request):
    auth_info = None
    try:
        if 'auth_info' in upload_request.files:
            auth_info = json.loads(upload_request.files['auth_info'].read().decode('utf-8'))
            if 'username' not in auth_info.keys() or 'password' not in auth_info.keys():
                return False, None, None

            username = auth_info['username']
            password = auth_info['password']
            user = models.User.by_username(username)

            if not user:
                user = models.User.by_email(username)

            if (not user or password != user.password_hash or user.status == models.UserStatusType.INACTIVE):
                return False, None, None

            return True, user, None

    except Exception as e:
        return False, None, e


def _create_upload_category_choices():
    ''' Turns categories in the database into a list of (id, name)s '''
    choices = [('', '[Select a category]')]
    for main_cat in models.MainCategory.query.order_by(models.MainCategory.id):
        choices.append((main_cat.id_as_string, main_cat.name, True))
        for sub_cat in main_cat.sub_categories:
            choices.append((sub_cat.id_as_string, ' - ' + sub_cat.name))
    return choices


# #################################### API ROUTES ####################################
def api_upload(upload_request, user):
    form_info = None
    try:
        form_info = json.loads(upload_request.files['torrent_info'].read().decode('utf-8'))

        form_info_as_dict = []
        for k, v in form_info.items():
            if k in ['is_anonymous', 'is_hidden', 'is_remake', 'is_complete']:
                if v == True:
                    form_info_as_dict.append((k, v))
            else:
                form_info_as_dict.append((k, v))
        form_info = ImmutableMultiDict(form_info_as_dict)

        # print(repr(form_info))
    except Exception as e:
        return flask.make_response(flask.jsonify({'Failure': ['Invalid data. See HELP in api_uploader.py']}), 400)

    try:
        torrent_file = upload_request.files['torrent_file']
        torrent_file = ImmutableMultiDict([('torrent_file', torrent_file)])

        # print(repr(torrent_file))
    except Exception as e:
        pass

    form = forms.UploadForm(CombinedMultiDict((torrent_file, form_info)))
    form.category.choices = _create_upload_category_choices()

    if upload_request.method == 'POST' and form.validate():
        torrent = backend.handle_torrent_upload(form, user, True)

        return flask.make_response(flask.jsonify({'Success': int('{0}'.format(torrent.id))}), 200)
    else:
        # print(form.errors)
        return_error_messages = []
        for error_name, error_messages in form.errors.items():
            # print(error_messages)
            return_error_messages.extend(error_messages)

        return flask.make_response(flask.jsonify({'Failure': return_error_messages}), 400)

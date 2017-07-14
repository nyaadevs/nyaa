import json
import os.path
from urllib.parse import quote

import flask
from werkzeug.datastructures import CombinedMultiDict

from sqlalchemy.orm import joinedload

from nyaa import backend, forms, models, torrents
from nyaa.extensions import db
from nyaa.utils import cached_function

app = flask.current_app
bp = flask.Blueprint('torrents', __name__)


@bp.route('/view/<int:torrent_id>', endpoint='view', methods=['GET', 'POST'])
def view_torrent(torrent_id):
    if flask.request.method == 'POST':
        torrent = models.Torrent.by_id(torrent_id)
    else:
        torrent = models.Torrent.query \
                                .options(joinedload('filelist'),
                                         joinedload('comments')) \
                                .filter_by(id=torrent_id) \
                                .first()
    if not torrent:
        flask.abort(404)

    # Only allow admins see deleted torrents
    if torrent.deleted and not (flask.g.user and flask.g.user.is_moderator):
        flask.abort(404)

    comment_form = None
    if flask.g.user:
        comment_form = forms.CommentForm()

    if flask.request.method == 'POST':
        if not flask.g.user:
            flask.abort(403)

        if comment_form.validate():
            comment_text = (comment_form.comment.data or '').strip()

            comment = models.Comment(
                torrent_id=torrent_id,
                user_id=flask.g.user.id,
                text=comment_text)

            db.session.add(comment)
            db.session.flush()

            torrent_count = torrent.update_comment_count()
            db.session.commit()

            flask.flash('Comment successfully posted.', 'success')

            return flask.redirect(flask.url_for('torrents.view',
                                                torrent_id=torrent_id,
                                                _anchor='com-' + str(torrent_count)))

    # Only allow owners and admins to edit torrents
    can_edit = flask.g.user and (flask.g.user is torrent.user or flask.g.user.is_moderator)

    files = None
    if torrent.filelist:
        files = json.loads(torrent.filelist.filelist_blob.decode('utf-8'))

    report_form = forms.ReportForm()
    return flask.render_template('view.html', torrent=torrent,
                                 files=files,
                                 comment_form=comment_form,
                                 comments=torrent.comments,
                                 can_edit=can_edit,
                                 report_form=report_form)


@bp.route('/view/<int:torrent_id>/edit', endpoint='edit', methods=['GET', 'POST'])
def edit_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)
    form = forms.EditForm(flask.request.form)
    form.category.choices = _create_upload_category_choices()

    editor = flask.g.user

    if not torrent:
        flask.abort(404)

    # Only allow admins edit deleted torrents
    if torrent.deleted and not (editor and editor.is_moderator):
        flask.abort(404)

    # Only allow torrent owners or admins edit torrents
    if not editor or not (editor is torrent.user or editor.is_moderator):
        flask.abort(403)

    if flask.request.method == 'POST' and form.validate():
        # Form has been sent, edit torrent with data.
        torrent.main_category_id, torrent.sub_category_id = \
            form.category.parsed_data.get_category_ids()
        torrent.display_name = (form.display_name.data or '').strip()
        torrent.information = (form.information.data or '').strip()
        torrent.description = (form.description.data or '').strip()

        torrent.hidden = form.is_hidden.data
        torrent.remake = form.is_remake.data
        torrent.complete = form.is_complete.data
        torrent.anonymous = form.is_anonymous.data

        if editor.is_trusted:
            torrent.trusted = form.is_trusted.data

        deleted_changed = torrent.deleted != form.is_deleted.data
        if editor.is_moderator:
            torrent.deleted = form.is_deleted.data

        url = flask.url_for('torrents.view', torrent_id=torrent.id)
        if deleted_changed and editor.is_moderator:
            log = "Torrent [#{0}]({1}) marked as {2}".format(
                torrent.id, url, "deleted" if torrent.deleted else "undeleted")
            adminlog = models.AdminLog(log=log, admin_id=editor.id)
            db.session.add(adminlog)

        db.session.commit()

        flask.flash(flask.Markup(
            'Torrent has been successfully edited! Changes might take a few minutes to show up.'),
            'info')

        return flask.redirect(url)
    else:
        if flask.request.method != 'POST':
            # Fill form data only if the POST didn't fail
            form.category.data = torrent.sub_category.id_as_string
            form.display_name.data = torrent.display_name
            form.information.data = torrent.information
            form.description.data = torrent.description

            form.is_hidden.data = torrent.hidden
            form.is_remake.data = torrent.remake
            form.is_complete.data = torrent.complete
            form.is_anonymous.data = torrent.anonymous

            form.is_trusted.data = torrent.trusted
            form.is_deleted.data = torrent.deleted

        return flask.render_template('edit.html',
                                     form=form,
                                     torrent=torrent)


@bp.route('/view/<int:torrent_id>/magnet')
def redirect_magnet(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent:
        flask.abort(404)

    return flask.redirect(torrents.create_magnet(torrent))


@bp.route('/view/<int:torrent_id>/torrent')
@bp.route('/download/<int:torrent_id>.torrent', endpoint='download')
def download_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent or not torrent.has_torrent:
        flask.abort(404)

    torrent_file, torrent_file_size = _get_cached_torrent_file(torrent)
    disposition = 'attachment; filename="{0}"; filename*=UTF-8\'\'{0}'.format(
        quote(torrent.torrent_name.encode('utf-8')))

    resp = flask.Response(torrent_file)
    resp.headers['Content-Type'] = 'application/x-bittorrent'
    resp.headers['Content-Disposition'] = disposition
    resp.headers['Content-Length'] = torrent_file_size
    return resp


@bp.route('/view/<int:torrent_id>/comment/<int:comment_id>/delete', methods=['POST'])
def delete_comment(torrent_id, comment_id):
    if not flask.g.user:
        flask.abort(403)
    torrent = models.Torrent.by_id(torrent_id)
    if not torrent:
        flask.abort(404)

    comment = models.Comment.query.filter_by(id=comment_id).first()
    if not comment:
        flask.abort(404)

    if not (comment.user.id == flask.g.user.id or flask.g.user.is_moderator):
        flask.abort(403)

    db.session.delete(comment)
    db.session.flush()
    torrent.update_comment_count()

    url = flask.url_for('torrents.view', torrent_id=torrent.id)
    if flask.g.user.is_moderator:
        log = "Comment deleted on torrent [#{}]({})".format(torrent.id, url)
        adminlog = models.AdminLog(log=log, admin_id=flask.g.user.id)
        db.session.add(adminlog)
    db.session.commit()

    flask.flash('Comment successfully deleted.', 'success')

    return flask.redirect(url)


@bp.route('/view/<int:torrent_id>/submit_report', endpoint='report', methods=['POST'])
def submit_report(torrent_id):
    if not flask.g.user:
        flask.abort(403)

    form = forms.ReportForm(flask.request.form)

    if flask.request.method == 'POST' and form.validate():
        report_reason = form.reason.data
        current_user_id = flask.g.user.id
        report = models.Report(
            torrent_id=torrent_id,
            user_id=current_user_id,
            reason=report_reason)

        db.session.add(report)
        db.session.commit()
        flask.flash('Successfully reported torrent!', 'success')

    return flask.redirect(flask.url_for('torrents.view', torrent_id=torrent_id))


@bp.route('/upload', methods=['GET', 'POST'])
def upload():
    upload_form = forms.UploadForm(CombinedMultiDict((flask.request.files, flask.request.form)))
    upload_form.category.choices = _create_upload_category_choices()

    if flask.request.method == 'POST' and upload_form.validate():
        torrent = backend.handle_torrent_upload(upload_form, flask.g.user)

        return flask.redirect(flask.url_for('torrents.view', torrent_id=torrent.id))
    else:
        # If we get here with a POST, it means the form data was invalid: return a non-okay status
        status_code = 400 if flask.request.method == 'POST' else 200
        return flask.render_template('upload.html', upload_form=upload_form), status_code


@cached_function
def _create_upload_category_choices():
    ''' Turns categories in the database into a list of (id, name)s '''
    choices = [('', '[Select a category]')]
    id_map = backend.get_category_id_map()

    for key in sorted(id_map.keys()):
        cat_names = id_map[key]
        is_main_cat = key.endswith('_0')

        # cat_name = is_main_cat and cat_names[0] or (' - ' + cat_names[1])
        cat_name = ' - '.join(cat_names)
        choices.append((key, cat_name, is_main_cat))
    return choices


def _get_cached_torrent_file(torrent):
    # Note: obviously temporary
    cached_torrent = os.path.join(app.config['BASE_DIR'],
                                  'torrent_cache', str(torrent.id) + '.torrent')
    if not os.path.exists(cached_torrent):
        with open(cached_torrent, 'wb') as out_file:
            out_file.write(torrents.create_bencoded_torrent(torrent))

    return open(cached_torrent, 'rb'), os.path.getsize(cached_torrent)

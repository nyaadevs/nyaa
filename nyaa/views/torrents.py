import json
from ipaddress import ip_address
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
                                .options(joinedload('filelist')) \
                                .filter_by(id=torrent_id) \
                                .first()

    if not torrent:
        flask.abort(404)

    # Only allow admins see deleted torrents
    if torrent.deleted and not (flask.g.user and flask.g.user.is_moderator):
        flask.abort(404)

    comment_form = None
    if flask.g.user and (not torrent.comment_locked or flask.g.user.is_moderator):
        comment_form = forms.CommentForm()

    if flask.request.method == 'POST':
        if not comment_form:
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

    torrent_comments = models.Comment.query.filter_by(
        torrent_id=torrent_id
    ).order_by(models.Comment.id.asc())

    report_form = forms.ReportForm()
    return flask.render_template('view.html', torrent=torrent,
                                 files=files,
                                 comment_form=comment_form,
                                 comments=torrent_comments,
                                 can_edit=can_edit,
                                 report_form=report_form)


@bp.route('/view/<int:torrent_id>/edit', endpoint='edit', methods=['GET', 'POST'])
def edit_torrent(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)
    form = forms.EditForm(flask.request.form)
    form.category.choices = _create_upload_category_choices()
    delete_form = forms.DeleteForm()
    ban_form = None

    editor = flask.g.user

    if not torrent:
        flask.abort(404)

    # Only allow admins edit deleted torrents
    if torrent.deleted and not (editor and editor.is_moderator):
        flask.abort(404)

    # Only allow torrent owners or admins edit torrents
    if not editor or not (editor is torrent.user or editor.is_moderator):
        flask.abort(403)

    torrent_user_level = torrent.user and torrent.user.level
    if editor and editor.is_moderator and \
            (torrent_user_level is None or editor.level > torrent_user_level):
        ban_form = forms.BanForm()

    if flask.request.method == 'POST' and form.submit.data and form.validate():
        # Form has been sent, edit torrent with data.
        torrent.main_category_id, torrent.sub_category_id = \
            form.category.parsed_data.get_category_ids()
        torrent.display_name = backend.sanitize_string((form.display_name.data or '').strip())
        torrent.information = backend.sanitize_string((form.information.data or '').strip())
        torrent.description = backend.sanitize_string((form.description.data or '').strip())

        torrent.hidden = form.is_hidden.data
        torrent.remake = form.is_remake.data
        torrent.complete = form.is_complete.data
        torrent.anonymous = form.is_anonymous.data
        if editor.is_trusted:
            torrent.trusted = form.is_trusted.data

        if editor.is_moderator:
            locked_changed = torrent.comment_locked != form.is_comment_locked.data
            torrent.comment_locked = form.is_comment_locked.data

        url = flask.url_for('torrents.view', torrent_id=torrent.id)
        if editor.is_moderator and locked_changed:
            log = "Torrent [#{0}]({1}) marked as {2}".format(
                torrent.id, url,
                "comments locked" if torrent.comment_locked else "comments unlocked")
            adminlog = models.AdminLog(log=log, admin_id=editor.id)
            db.session.add(adminlog)

        db.session.commit()

        flask.flash(flask.Markup(
            'Torrent has been successfully edited! Changes might take a few minutes to show up.'),
            'success')

        url = flask.url_for('torrents.view', torrent_id=torrent.id)
        return flask.redirect(url)
    elif flask.request.method == 'POST' and delete_form.validate() and \
            (not ban_form or ban_form.validate()):
        return _delete_torrent(torrent, delete_form, ban_form)
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
            form.is_comment_locked.data = torrent.comment_locked

        ipbanned = None
        if editor.is_moderator:
            torrent_ip_banned = True
            user_ip_banned = True

            # Archived torrents do not have a null uploader_ip
            if torrent.uploader_ip:
                torrent_ip_banned = models.Ban.banned(None, torrent.uploader_ip).first()

            if torrent.user:
                user_ip_banned = models.Ban.banned(None, torrent.user.last_login_ip).first()
            ipbanned = (torrent_ip_banned and user_ip_banned)

        return flask.render_template('edit.html',
                                     form=form,
                                     delete_form=delete_form,
                                     ban_form=ban_form,
                                     torrent=torrent,
                                     ipbanned=ipbanned)


def _delete_torrent(torrent, form, banform):
    editor = flask.g.user
    uploader = torrent.user

    # Only allow admins edit deleted torrents
    if torrent.deleted and not (editor and editor.is_moderator):
        flask.abort(404)

    action = None
    url = flask.url_for('main.home')

    ban_torrent = form.ban.data
    if banform:
        ban_torrent = ban_torrent or banform.ban_user.data or banform.ban_userip.data

    if form.delete.data and not torrent.deleted:
        action = 'deleted'
        torrent.deleted = True
        db.session.add(torrent)

    elif ban_torrent and not torrent.banned and editor.is_moderator:
        action = 'banned'
        torrent.banned = True
        if not torrent.deleted:
            torrent.deleted = True
            action = 'deleted and banned'
        db.session.add(models.TrackerApi(torrent.info_hash, 'remove'))
        torrent.stats.seed_count = 0
        torrent.stats.leech_count = 0
        db.session.add(torrent)

    elif form.undelete.data and torrent.deleted:
        action = 'undeleted'
        torrent.deleted = False
        if torrent.banned:
            action = 'undeleted and unbanned'
            torrent.banned = False
            db.session.add(models.TrackerApi(torrent.info_hash, 'insert'))
        db.session.add(torrent)

    elif form.unban.data and torrent.banned:
        action = 'unbanned'
        torrent.banned = False
        db.session.add(models.TrackerApi(torrent.info_hash, 'insert'))
        db.session.add(torrent)

    if not action and not ban_torrent:
        flask.flash(flask.Markup('What the fuck are you doing?'), 'danger')
        return flask.redirect(flask.url_for('torrents.edit', torrent_id=torrent.id))

    if action and editor.is_moderator:
        url = flask.url_for('torrents.view', torrent_id=torrent.id)
        if editor is not uploader:
            log = "Torrent [#{0}]({1}) has been {2}".format(torrent.id, url, action)
            adminlog = models.AdminLog(log=log, admin_id=editor.id)
            db.session.add(adminlog)

    if action:
        db.session.commit()
        flask.flash(flask.Markup('Torrent has been successfully {0}.'.format(action)), 'success')

    if not banform or not (banform.ban_user.data or banform.ban_userip.data):
        return flask.redirect(url)

    if banform.ban_userip.data:
        tbanned = models.Ban.banned(None, torrent.uploader_ip).first()
        ubanned = True
        if uploader:
            ubanned = models.Ban.banned(None, uploader.last_login_ip).first()
        ipbanned = (tbanned and ubanned)

    if (banform.ban_user.data and (not uploader or uploader.is_banned)) or \
            (banform.ban_userip.data and ipbanned):
        flask.flash(flask.Markup('What the fuck are you doing?'), 'danger')
        return flask.redirect(flask.url_for('torrents.edit', torrent_id=torrent.id))

    flavor = "Nyaa" if app.config['SITE_FLAVOR'] == 'nyaa' else "Sukebei"
    eurl = flask.url_for('torrents.view', torrent_id=torrent.id, _external=True)
    reason = "[{0}#{1}]({2}) {3}".format(flavor, torrent.id, eurl, banform.reason.data)
    ban1 = models.Ban(admin_id=editor.id, reason=reason)
    ban2 = models.Ban(admin_id=editor.id, reason=reason)
    db.session.add(ban1)

    if uploader:
        uploader.status = models.UserStatusType.BANNED
        db.session.add(uploader)
        ban1.user_id = uploader.id
        ban2.user_id = uploader.id

    if banform.ban_userip.data:
        if not ubanned:
            ban1.user_ip = ip_address(uploader.last_login_ip)
            if not tbanned:
                uploader_ip = ip_address(torrent.uploader_ip)
                if ban1.user_ip != uploader_ip:
                    ban2.user_ip = uploader_ip
                    db.session.add(ban2)
        else:
            ban1.user_ip = ip_address(torrent.uploader_ip)

    uploader_str = "Anonymous"
    if uploader:
        uploader_url = flask.url_for('users.view_user', user_name=uploader.username)
        uploader_str = "[{0}]({1})".format(uploader.username, uploader_url)
    if ban1.user_ip:
        uploader_str += " IP({0})".format(ban1.user_ip)
        ban1.user_ip = ban1.user_ip.packed
    if ban2.user_ip:
        uploader_str += " IP({0})".format(ban2.user_ip)
        ban2.user_ip = ban2.user_ip.packed

    log = "Uploader {0} of torrent [#{1}]({2}) has been banned.".format(
        uploader_str, torrent.id, flask.url_for('torrents.view', torrent_id=torrent.id), action)
    adminlog = models.AdminLog(log=log, admin_id=editor.id)
    db.session.add(adminlog)

    db.session.commit()

    flask.flash(flask.Markup('Uploader has been successfully banned.'), 'success')

    return flask.redirect(url)


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

    if torrent.deleted and not (flask.g.user and flask.g.user.is_moderator):
        flask.abort(404)

    torrent_file, torrent_file_size = _make_torrent_file(torrent)
    disposition = 'inline; filename="{0}"; filename*=UTF-8\'\'{0}'.format(
        quote(torrent.torrent_name.encode('utf-8')))

    resp = flask.Response(torrent_file)
    resp.headers['Content-Type'] = 'application/x-bittorrent'
    resp.headers['Content-Disposition'] = disposition
    resp.headers['Content-Length'] = torrent_file_size
    return resp


@bp.route('/view/<int:torrent_id>/comment/<int:comment_id>/edit', methods=['POST'])
def edit_comment(torrent_id, comment_id):
    if not flask.g.user:
        flask.abort(403)
    torrent = models.Torrent.by_id(torrent_id)
    if not torrent:
        flask.abort(404)

    comment = models.Comment.query.get(comment_id)
    if not comment:
        flask.abort(404)

    if not comment.user.id == flask.g.user.id:
        flask.abort(403)

    if torrent.comment_locked and not flask.g.user.is_moderator:
        flask.abort(403)

    if comment.editing_limit_exceeded:
        flask.abort(flask.make_response(flask.jsonify(
            {'error': 'Editing time limit exceeded.'}), 400))

    form = forms.CommentForm(flask.request.form)

    if not form.validate():
        error_str = ' '.join(form.errors)
        flask.abort(flask.make_response(flask.jsonify({'error': error_str}), 400))

    comment.text = form.comment.data
    db.session.commit()

    return flask.jsonify({'comment': comment.text})


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

    if not (comment.user.id == flask.g.user.id or flask.g.user.is_superadmin):
        flask.abort(403)

    if torrent_id != comment.torrent_id:
        flask.abort(400)

    if torrent.comment_locked and not flask.g.user.is_moderator:
        flask.abort(403)

    if comment.editing_limit_exceeded and not flask.g.user.is_superadmin:
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
    if not flask.g.user or flask.g.user.age < app.config['RATELIMIT_ACCOUNT_AGE']:
        flask.abort(403)

    form = forms.ReportForm(flask.request.form)
    torrent = models.Torrent.by_id(torrent_id)
    if not torrent:
        flask.abort(404)
    if torrent.banned:
        flask.flash("The torrent you've tried to report is already banned.", 'danger')
        flask.abort(404)

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
    elif len(form.reason.data) == 0:
        flask.flash('Please give a report reason!', 'danger')

    return flask.redirect(flask.url_for('torrents.view', torrent_id=torrent_id))


@bp.route('/upload', methods=['GET', 'POST'])
def upload():
    upload_form = forms.UploadForm(CombinedMultiDict((flask.request.files, flask.request.form)))
    upload_form.category.choices = _create_upload_category_choices()

    show_ratelimit = False
    next_upload_time = None
    ratelimit_count = 0

    # Anonymous uploaders and non-trusted uploaders

    no_or_new_account = (not flask.g.user
                         or (flask.g.user.age < app.config['RATELIMIT_ACCOUNT_AGE']
                             and not flask.g.user.is_trusted))

    if app.config['RATELIMIT_UPLOADS'] and no_or_new_account:
        now, ratelimit_count, next_upload_time = backend.check_uploader_ratelimit(flask.g.user)
        show_ratelimit = ratelimit_count >= app.config['MAX_UPLOAD_BURST']
        next_upload_time = next_upload_time if next_upload_time > now else None

    if flask.request.method == 'POST' and upload_form.validate():
        try:
            torrent = backend.handle_torrent_upload(upload_form, flask.g.user)

            return flask.redirect(flask.url_for('torrents.view', torrent_id=torrent.id))
        except backend.TorrentExtraValidationException:
            pass

    # If we get here with a POST, it means the form data was invalid: return a non-okay status
    status_code = 400 if flask.request.method == 'POST' else 200
    return flask.render_template('upload.html',
                                 upload_form=upload_form,
                                 show_ratelimit=show_ratelimit,
                                 ratelimit_count=ratelimit_count,
                                 next_upload_time=next_upload_time), status_code


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


def _make_torrent_file(torrent):
    with open(torrent.info_dict_path, 'rb') as in_file:
        bencoded_info = in_file.read()

    bencoded_torrent_data = torrents.create_bencoded_torrent(torrent, bencoded_info)

    return bencoded_torrent_data, len(bencoded_torrent_data)

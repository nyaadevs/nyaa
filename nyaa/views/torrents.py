import json

import flask

from sqlalchemy.orm import joinedload

from nyaa import db, forms, models

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

import os.path
from urllib.parse import quote

import flask

from nyaa import api_handler, app, db, forms, models, template_utils, torrents, views
from nyaa.backend import get_category_id_map

DEBUG_API = False


@app.template_global()
def category_name(cat_id):
    ''' Given a category id (eg. 1_2), returns a category name (eg. Anime - English-translated) '''
    return ' - '.join(get_category_id_map().get(cat_id, ['???']))


# Routes start here #

@app.route('/view/<int:torrent_id>/comment/<int:comment_id>/delete', methods=['POST'])
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


@app.route('/view/<int:torrent_id>/magnet')
def redirect_magnet(torrent_id):
    torrent = models.Torrent.by_id(torrent_id)

    if not torrent:
        flask.abort(404)

    return flask.redirect(torrents.create_magnet(torrent))


@app.route('/view/<int:torrent_id>/torrent')
@app.route('/download/<int:torrent_id>.torrent')
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


@app.route('/view/<int:torrent_id>/submit_report', methods=['POST'])
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


def _get_cached_torrent_file(torrent):
    # Note: obviously temporary
    cached_torrent = os.path.join(app.config['BASE_DIR'],
                                  'torrent_cache', str(torrent.id) + '.torrent')
    if not os.path.exists(cached_torrent):
        with open(cached_torrent, 'wb') as out_file:
            out_file.write(torrents.create_bencoded_torrent(torrent))

    return open(cached_torrent, 'rb'), os.path.getsize(cached_torrent)


# #################################### BLUEPRINTS ####################################

def register_blueprints(flask_app):
    """ Register the blueprints using the flask_app object """

    # Template filters and globals
    flask_app.register_blueprint(template_utils.bp)
    # API routes
    flask_app.register_blueprint(api_handler.api_blueprint, url_prefix='/api')
    # Site routes
    flask_app.register_blueprint(views.account_bp)
    flask_app.register_blueprint(views.admin_bp)
    flask_app.register_blueprint(views.main_bp)
    flask_app.register_blueprint(views.site_bp)
    flask_app.register_blueprint(views.torrents_bp)
    flask_app.register_blueprint(views.users_bp)


# When done, this can be moved to nyaa/__init__.py instead of importing this file
register_blueprints(app)

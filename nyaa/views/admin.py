from ipaddress import ip_address

import flask

from nyaa import forms, models
from nyaa.extensions import db

bp = flask.Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/log', endpoint='log', methods=['GET'])
def view_adminlog():
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)

    page = flask.request.args.get('p', flask.request.args.get('offset', 1, int), int)
    logs = models.AdminLog.all_logs() \
        .order_by(models.AdminLog.created_time.desc()) \
        .paginate(page=page, per_page=20)

    return flask.render_template('adminlog.html',
                                 adminlog=logs)


@bp.route('/bans', endpoint='bans', methods=['GET', 'POST'])
def view_adminbans():
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)

    form = forms.StringSubmitForm()
    if flask.request.method == 'POST' and form.validate():
        ban = models.Ban.by_id(form.submit.data)
        if not ban:
            flask.abort(404)

        log = 'Unbanned ban #{0}'.format(ban.id)

        if ban.user:
            log += ' ' + ban.user.username
            ban.user.status = models.UserStatusType.ACTIVE
            db.session.add(ban.user)

        if ban.user_ip:
            log += ' IP({0})'.format(ip_address(ban.user_ip))

        adminlog = models.AdminLog(log=log, admin_id=flask.g.user.id)
        db.session.add(adminlog)

        db.session.delete(ban)
        db.session.commit()

        flask.flash('Unbanned ban #{0}'.format(ban.id), 'success')

    page = flask.request.args.get('p', flask.request.args.get('offset', 1, int), int)
    bans = models.Ban.all_bans() \
        .order_by(models.Ban.created_time.desc()) \
        .paginate(page=page, per_page=20)

    return flask.render_template('admin_bans.html',
                                 bans=bans,
                                 form=form)


@bp.route('/reports', endpoint='reports', methods=['GET', 'POST'])
def view_reports():
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)

    page = flask.request.args.get('p', flask.request.args.get('offset', 1, int), int)
    reports = models.Report.not_reviewed(page)
    report_action = forms.ReportActionForm(flask.request.form)

    if flask.request.method == 'POST' and report_action.validate():
        action = report_action.action.data
        torrent_id = report_action.torrent.data
        report_id = report_action.report.data
        torrent = models.Torrent.by_id(torrent_id)
        report = models.Report.by_id(report_id)

        if not torrent or not report or report.status != 0:
            flask.abort(404)

        report_user = models.User.by_id(report.user_id)
        log = 'Report #{}: {} [#{}]({}), reported by [{}]({})'
        if action == 'delete':
            torrent.deleted = True
            report.status = 1
            log = log.format(report_id, 'Deleted', torrent_id,
                             flask.url_for('torrents.view', torrent_id=torrent_id),
                             report_user.username,
                             flask.url_for('users.view_user', user_name=report_user.username))
        elif action == 'hide':
            log = log.format(report_id, 'Hid', torrent_id,
                             flask.url_for('torrents.view', torrent_id=torrent_id),
                             report_user.username,
                             flask.url_for('users.view_user', user_name=report_user.username))
            torrent.hidden = True
            report.status = 1
        else:
            log = log.format(report_id, 'Closed', torrent_id,
                             flask.url_for('torrents.view', torrent_id=torrent_id),
                             report_user.username,
                             flask.url_for('users.view_user', user_name=report_user.username))
            report.status = 2

        adminlog = models.AdminLog(log=log, admin_id=flask.g.user.id)
        db.session.add(adminlog)

        models.Report.remove_reviewed(torrent_id)
        db.session.commit()
        flask.flash('Closed report #{}'.format(report.id), 'success')
        return flask.redirect(flask.url_for('admin.reports'))

    return flask.render_template('reports.html',
                                 reports=reports,
                                 report_action=report_action)

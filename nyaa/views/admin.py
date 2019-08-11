from datetime import datetime
from ipaddress import ip_address

import flask

from nyaa import email, forms, models
from nyaa.extensions import db

app = flask.current_app
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


@bp.route('/trusted/<list_filter>', endpoint='trusted', methods=['GET'])
@bp.route('/trusted', endpoint='trusted', methods=['GET'])
def view_trusted(list_filter=None):
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)

    page = flask.request.args.get('p', flask.request.args.get('offset', 1, int), int)
    q = db.session.query(models.TrustedApplication)
    if list_filter == 'closed':
        q = q.filter_by(is_closed=True)
    else:
        q = q.filter_by(is_closed=False)
        if list_filter == 'new':
            q = q.filter_by(is_new=True)
        elif list_filter == 'reviewed':
            q = q.filter_by(is_reviewed=True)
        elif list_filter is not None:
            flask.abort(404)
    apps = q.order_by(models.TrustedApplication.created_time.desc()) \
            .paginate(page=page, per_page=20)

    return flask.render_template('admin_trusted.html', apps=apps,
                                 list_filter=list_filter)


@bp.route('/trusted/application/<int:app_id>', endpoint='trusted_application',
          methods=['GET', 'POST'])
def view_trusted_application(app_id):
    if not flask.g.user or not flask.g.user.is_moderator:
        flask.abort(403)
    app = models.TrustedApplication.by_id(app_id)
    if not app:
        flask.abort(404)
    decision_form = None
    review_form = forms.TrustedReviewForm(flask.request.form)
    if flask.g.user.is_superadmin and not app.is_closed:
        decision_form = forms.TrustedDecisionForm()
    if flask.request.method == 'POST':
        do_decide = decision_form and (decision_form.accept.data or decision_form.reject.data)
        if do_decide and decision_form.validate():
            app.closed_time = datetime.utcnow()
            if decision_form.accept.data:
                app.status = models.TrustedApplicationStatus.ACCEPTED
                app.submitter.level = models.UserLevelType.TRUSTED
                flask.flash(flask.Markup('Application has been <b>accepted</b>.'), 'success')
            elif decision_form.reject.data:
                app.status = models.TrustedApplicationStatus.REJECTED
                flask.flash(flask.Markup('Application has been <b>rejected</b>.'), 'success')
            _send_trusted_decision_email(app.submitter, bool(decision_form.accept.data))
            db.session.commit()
            return flask.redirect(flask.url_for('admin.trusted_application', app_id=app_id))
        elif review_form.comment.data and review_form.validate():
            tr = models.TrustedReview()
            tr.reviewer_id = flask.g.user.id
            tr.app_id = app_id
            tr.comment = review_form.comment.data
            tr.recommendation = getattr(models.TrustedRecommendation,
                                        review_form.recommendation.data.upper())
            if app.status == models.TrustedApplicationStatus.NEW:
                app.status = models.TrustedApplicationStatus.REVIEWED
            db.session.add(tr)
            db.session.commit()
            flask.flash('Review successfully posted.', 'success')
            return flask.redirect(flask.url_for('admin.trusted_application', app_id=app_id))

    return flask.render_template('admin_trusted_view.html', app=app, review_form=review_form,
                                 decision_form=decision_form)


def _send_trusted_decision_email(user, is_accepted):
    email_msg = email.EmailHolder(
        subject='Your {} Trusted Application was {}.'.format(app.config['GLOBAL_SITE_NAME'],
                                                             ('rejected', 'accepted')[is_accepted]),
        recipient=user,
        text=flask.render_template('email/trusted.txt', is_accepted=is_accepted),
        html=flask.render_template('email/trusted.html', is_accepted=is_accepted),
    )

    email.send_email(email_msg)

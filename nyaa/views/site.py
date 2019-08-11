import flask

bp = flask.Blueprint('site', __name__)


# @bp.route('/about', methods=['GET'])
# def about():
#     return flask.render_template('about.html')


@bp.route('/rules', methods=['GET'])
def rules():
    return flask.render_template('rules.html')


@bp.route('/help', methods=['GET'])
def help():
    return flask.render_template('help.html')


@bp.route('/xmlns/nyaa', methods=['GET'])
def xmlns_nyaa():
    return flask.render_template('xmlns.html')


@bp.route('/trusted', methods=['GET'])
def trusted():
    return flask.render_template('trusted.html')

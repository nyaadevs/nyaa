import flask

from nyaa import app, db
from nyaa.search import search

TORZNAB_ERRORS = {
    100: 'Incorrect user credentials',
    101: 'Account suspended',
    102: 'Insufficient priviledges/not authorized',
    103: 'Registration denied',
    104: 'Registrations are closed',
    105: 'Invalid registration (Email Address Taken)',
    106: 'Invalid registration (Email Address Bad Format)',
    107: 'Registration Failed (Data error)',

    200: 'Missing parameter',
    201: 'Incorrect parameter',
    202: 'No such function. (Function not defined in this specification)',
    203: 'Function not available. (Optional function is not implemented)',

    300: 'No such item',

    500: 'Request limit reached',
    501: 'Download limit reached',

    900: 'Unknown error',

    901: 'API Disabled'
}

# TODO: For Nyaa specific, should be stored in config or db somewhere.
TORZNAB_CATEGORY_MAP = {
    3000: [100201, 100202],
    3010: [],
    3040: [100201],
    3060: [100202],
    4000: [100602],
    4050: [100602],
    5000: [100102],
    5070: [100102],
    7000: [100301, 100302],
    7020: [100301],
    7620: [100302]
}


@app.template_global()
def get_torznab_categories(torrent):
    categories = []
    main_cat_id = torrent.main_category.id
    sub_cat_id = torrent.sub_category.id
    site_cat = 100000 + main_cat_id * 100 + sub_cat_id

    # Add the 101 category for ease of use.
    categories.append(main_cat_id * 100 + sub_cat_id)

    # Add torznab/newznab generic range categories.
    # TODO: Don't use a hardcoded list, use a cached list from the database.
    for key, value in TORZNAB_CATEGORY_MAP.items():
        if site_cat in value:
            categories.append(key)

    # Add torznab/newznab site-specific range categories
    if sub_cat_id > 0:
        categories.append(100000 + main_cat_id * 100)
    categories.append(100000 + main_cat_id * 100 + sub_cat_id)
    
    return categories

def render_torznab_error(code):
    # TODO: Check Accept header and set Cache-Control.
    description = TORZNAB_ERRORS[code]
    torznab_xml = flask.render_template('torznab/error.xml',
                                        code=code,
                                        description=description)
    response = flask.make_response(torznab_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


def render_torznab_caps():
    # TODO: Check Accept header and set Cache-Control.
    torznab_xml = flask.render_template('torznab/caps.xml')
    response = flask.make_response(torznab_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


def render_torznab_feed(query, offset, extended):
    # TODO: Check Accept header and set Cache-Control.
    torznab_xml = flask.render_template('torznab/feed.xml',
                                        query=query,
                                        offset=offset,
                                        extended=extended)
    response = flask.make_response(torznab_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


def torznab_caps():
    return render_torznab_caps()


def torznab_search():
    page_size = app.config['RESULTS_PER_PAGE']

    # Default newznab query params, return empty result if unsupported to prevent clients from accessing the api as a traditional newznab indexer.
    q = flask.request.args.get('q')
    season = flask.request.args.get('season')
    ep = flask.request.args.get('ep')
    rid = flask.request.args.get('rid')

    cat = flask.request.args.get('cat', default='100000')

    # Quality filter (remake/trusted) has no predefined query param yet. Propose 'tag' as generic cross newznab/torznab field to remain site agnostic.
    #quality_filter = flask.request.args.get('f')
    extended = flask.request.args.get('extended')
    offset = flask.request.args.get('offset', default=0, type=int)
    limit = flask.request.args.get('limit', default=page_size, type=int)

    if season or ep or rid:
        return render_torznab_error(201)

    page = int(1 + offset / page_size)
    # TODO: Cleanup q
    # TODO: category can have multiple, yet search does not support that.
    category = None
    quality_filter = None
    # TODO: offset = usually per page, but not guaranteed, give error if not a multiple of page size.
    #       Or fix search module to accept offset & limit instead of page.
    # TODO: maximum of limit should be the app.config['RESULTS_PER_PAGE']
    query_args = {
        'term': q or '',
        'category': category or '0_0',
        'quality_filter': quality_filter or '0',
        'page': page or 1,
        'rss': False  # We want it to page
    }

    # God mode
    if flask.g.user and flask.g.user.is_admin:
        query_args['admin'] = True

    query = search(**query_args)

    return render_torznab_feed(query, offset, extended)


def handle_api_request(api_request):
    apikey = api_request.args.get('apikey')
    mode = api_request.args.get('t')

    if mode == 'caps':
        return torznab_caps()

    if mode == 'search':
        return torznab_search()

    if mode == 'tvsearch':
        return torznab_search()

    if mode == 'register':
        return render_torznab_error(103)

    # modes specified in the newznab spec that are not supported.
    if mode in ['movie', 'music', 'book',
                'details', 'getnfo', 'get',
                'cartadd', 'cartdel', 'comments', 'commentadd', 'user']:
        return render_torznab_error(203)

    return render_torznab_error(202)

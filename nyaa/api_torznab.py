import flask
import re

from nyaa import app, db, models
from nyaa.search import search_custom, EmptySearchResult, EmptySearchError

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

TORZNAB_RESULTS_PER_PAGE = 100


@app.template_global()
def get_torznab_categories(torrent):
    categories = []
    main_cat_id = torrent.main_category.id
    sub_cat_id = torrent.sub_category.id
    site_cat = 100000 + main_cat_id * 100 + sub_cat_id

    # Add the 101 category for ease of use.
    if sub_cat_id > 0:
        categories.append(main_cat_id * 100)
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

def get_torznab_categorymap():
    return models.MainCategory.query

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
    category_map = get_torznab_categorymap()
    # TODO: Check Accept header and set Cache-Control.
    torznab_xml = flask.render_template('torznab/caps.xml',
                                        page_size=TORZNAB_RESULTS_PER_PAGE,
                                        categories=category_map)
    response = flask.make_response(torznab_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


def render_torznab_feed(query_results, offset, extended):
    # TODO: Check Accept header and set Cache-Control.
    torznab_xml = flask.render_template('torznab/feed.xml',
                                        torrent_query=query_results,
                                        offset=offset,
                                        extended=extended)
    response = flask.make_response(torznab_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


def torznab_caps():
    return render_torznab_caps()


def get_categories_filter(cat):
    categories = []
    if cat:
        for item in cat.split(','):
            # Parse 1_1 format for compatibility
            cat_match = re.match(r'^(\d+)_(\d+)$', item)
            if cat_match:
                item = int(cat_match.group(1)) * 100 + int(cat_match.group(2))

            num = int(item)
            if num >= 100000:
                categories.append(num - 100000)
            elif num >= 1000:
                categories.extend([x - 100000 for x in TORZNAB_CATEGORY_MAP.get(num, [])])
            elif num > 0:
                categories.append(num)

        # Check if any of the specified categories 'stuck'.
        if not categories:
            raise EmptySearchError('Categories {} guaranteed to produce empty result'.format(cat))
    return categories

def get_tag_filter(tag):
    include_tags = []
    exclude_tags = []
    if tag:
        for item in tag.split(','):
            if item[0] == '!':
                exclude_tags.append(item[1:].lower())
            else:
                include_tags.append(item.lower())
    for incl in include_tags:
        if incl in exclude_tags:
            raise EmptySearchError('Tag {} both required and filtered')
    return (include_tags, exclude_tags)

def torznab_search(api_request):
    page_size = TORZNAB_RESULTS_PER_PAGE

    # Default newznab query params, return empty result if unsupported to prevent clients from accessing the api as a traditional newznab indexer.
    query_term = api_request.args.get('q')
    query_season = api_request.args.get('season')
    query_episode = api_request.args.get('ep')
    query_rageid = api_request.args.get('rid')

    if query_season is not None or query_episode is not None or query_rageid is not None:
        return render_torznab_error(201)

    cat = api_request.args.get('cat', default='')
    # Quality filter (remake/trusted) has no predefined query param yet.
    # Propose 'tag' as generic cross newznab/torznab field to remain site agnostic.
    tag = api_request.args.get('tag', default='')
    extended = api_request.args.get('extended', False, type=bool)
    offset = api_request.args.get('offset', default=0, type=int)
    limit = api_request.args.get('limit', default=page_size, type=int)

    try:
        limit = min(limit, page_size)
        if limit == 0:
            raise EmptySearchError('Limit of 0 guaranteed guarantees empty result')
        if offset % limit:
            app.logger.warn('offset {} isn\'t a multiple of the page size {}'.format(offset, limit))
            return render_torznab_error(201)

        categories = get_categories_filter(cat)

        (include_tags, exclude_tags) = get_tag_filter(tag)

        # TODO: Cleanup q

        query_args = {
            'term': query_term,
            'categories': categories,
            'include_tags': include_tags,
            'exclude_tags': exclude_tags,
            'page': 1 + int(offset / limit),
            'page_size': limit
        }

        query_results = search_custom(**query_args)
    except EmptySearchError:
        query_results = EmptySearchResult()

    return render_torznab_feed(query_results, offset, extended)


def handle_api_request(api_request):
    #apikey = api_request.args.get('apikey')
    mode = api_request.args.get('t')

    if mode == 'caps':
        return torznab_caps()

    elif mode == 'search':
        return torznab_search(api_request)

    elif mode == 'tvsearch':
        return torznab_search(api_request)

    elif mode == 'register':
        return render_torznab_error(103)

    # modes specified in the newznab spec that are not supported.
    elif mode in ['movie', 'music', 'book',
                  'details', 'getnfo', 'get',
                  'cartadd', 'cartdel', 'comments', 'commentadd', 'user']:
        return render_torznab_error(203)

    else:
        return render_torznab_error(202)

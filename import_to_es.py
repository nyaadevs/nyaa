#!/usr/bin/env python
"""
Bulk load torents from mysql into elasticsearch `nyaav2` index,
which is assumed to already exist.
This is a one-shot deal, so you'd either need to complement it
with a cron job or some binlog-reading thing (TODO)
"""
import sys
import json

# This should be progressbar33
import progressbar
from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch import helpers

from nyaa import create_app, models
from nyaa.extensions import db

app = create_app('config')
es = Elasticsearch(hosts=app.config['ES_HOSTS'], timeout=30)
ic = IndicesClient(es)

def pad_bytes(in_bytes, size):
    return in_bytes + (b'\x00' * max(0, size - len(in_bytes)))

# turn into thing that elasticsearch indexes. We flatten in
# the stats (seeders/leechers) so we can order by them in es naturally.
# we _don't_ dereference uploader_id to the user's display name however,
# instead doing that at query time. I _think_ this is right because
# we don't want to reindex all the user's torrents just because they
# changed their name, and we don't really want to FTS search on the user anyway.
# Maybe it's more convenient to derefence though.
def mk_es(t, index_name):
    return {
        "_id": t.id,
        "_index": index_name,
        "_source": {
            # we're also indexing the id as a number so you can
            # order by it. seems like this is just equivalent to
            # order by created_time, but oh well
            "id": t.id,
            "display_name": t.display_name,
            "created_time": t.created_time,
            # not analyzed but included so we can render magnet links
            # without querying sql again.
            "info_hash": pad_bytes(t.info_hash, 20).hex(),
            "filesize": t.filesize,
            "uploader_id": t.uploader_id,
            "main_category_id": t.main_category_id,
            "sub_category_id": t.sub_category_id,
            "comment_count": t.comment_count,
            # XXX all the bitflags are numbers
            "anonymous": bool(t.anonymous),
            "trusted": bool(t.trusted),
            "remake": bool(t.remake),
            "complete": bool(t.complete),
            # TODO instead of indexing and filtering later
            # could delete from es entirely. Probably won't matter
            # for at least a few months.
            "hidden": bool(t.hidden),
            "deleted": bool(t.deleted),
            "has_torrent": t.has_torrent,
            # Stats
            "download_count": t.stats.download_count,
            "leech_count": t.stats.leech_count,
            "seed_count": t.stats.seed_count,
        }
    }

# page through an sqlalchemy query, like the per_fetch but
# doesn't break the eager joins its doing against the stats table.
# annoying that this isn't built in somehow.
def page_query(query, limit=sys.maxsize, batch_size=10000, progress_bar=None):
    start = 0
    while True:
        # XXX very inelegant way to do this, i'm confus
        stop = min(limit, start + batch_size)
        if stop == start:
            break
        things = query.slice(start, stop)
        if not things:
            break
        had_things = False
        for thing in things:
            had_things = True
            yield(thing)
        if not had_things or stop == limit:
            break
        if progress_bar:
            progress_bar.update(start)
        start = min(limit, start + batch_size)

FLAVORS = [
    ('nyaa', models.NyaaTorrent),
    ('sukebei', models.SukebeiTorrent)
]

# Get binlog status from mysql
with app.app_context():
    master_status = db.engine.execute('SHOW MASTER STATUS;').fetchone()

    position_json = {
        'log_file': master_status[0],
        'log_pos': master_status[1]
    }

    print('Save the following in the file configured in your ES sync config JSON:')
    print(json.dumps(position_json))

    for flavor, torrent_class in FLAVORS:
        print('Importing torrents for index', flavor, 'from', torrent_class)
        bar = progressbar.ProgressBar(
            maxval=torrent_class.query.count(),
            widgets=[ progressbar.SimpleProgress(),
                      ' [', progressbar.Timer(), '] ',
                      progressbar.Bar(),
                      ' (', progressbar.ETA(), ') ',
                ])

        # turn off refreshes while bulk loading
        ic.put_settings(body={'index': {'refresh_interval': '-1'}}, index=flavor)

        bar.start()
        helpers.bulk(es, (mk_es(t, flavor) for t in page_query(torrent_class.query, progress_bar=bar)), chunk_size=10000)
        bar.finish()

        # Refresh the index immideately
        ic.refresh(index=flavor)
        print('Index refresh done.')

        # restore to near-enough real time
        ic.put_settings(body={'index': {'refresh_interval': '30s'}}, index=flavor)

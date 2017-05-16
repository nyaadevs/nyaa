#!/usr/bin/env python
"""
stream changes in mysql (on the torrents and statistics table) into
elasticsearch as they happen on the binlog. This keeps elasticsearch in sync
with whatever you do to the database, including stuff like admin queries. Also,
because mysql keeps the binlog around for N days before deleting old stuff, you
can survive a hiccup of elasticsearch or this script dying and pick up where
you left off.

For that "picking up" part, this script depends on one piece of external state:
its last known binlog filename and position. This is saved off as a JSON file
to a configurable location on the filesystem periodically. If the file is not
present then you can initialize it with the values from `SHOW MASTER STATUS`
from the mysql repl, which will start the sync from current state.

In the case of catastrophic elasticsearch meltdown where you need to
reconstruct the index, you'll want to be a bit careful with coordinating
sync_es and import_to_es scripts. If you run import_to_es first than run
sync_es against SHOW MASTER STATUS, anything that changed the database between
when import_to_es and sync_es will be lost. Instead, you can run SHOW MASTER
STATUS _before_ you run import_to_es. That way you'll definitely pick up any
changes that happen while the import_to_es script is dumping stuff from the
database into es, at the expense of redoing a (small) amount of indexing.
"""
from elasticsearch import Elasticsearch
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import UpdateRowsEvent, DeleteRowsEvent, WriteRowsEvent
from datetime import datetime
from nyaa.models import TorrentFlags
import sys
import json
import time
import logging

logging.basicConfig()

log = logging.getLogger('sync_es')
log.setLevel(logging.INFO)

#logging.getLogger('elasticsearch').setLevel(logging.DEBUG)

# in prod want in /var/lib somewhere probably
SAVE_LOC = "/var/lib/sync_es_position.json"
MYSQL_HOST = '127.0.0.1'
MYSQL_PORT = 3306
MYSQL_USER = 'test'
MYSQL_PW = 'test123'
NT_DB = 'nyaav2'

with open(SAVE_LOC) as f:
    pos = json.load(f)

es = Elasticsearch()

stream = BinLogStreamReader(
        # TODO parse out from config.py or something
        connection_settings = {
            'host': MYSQL_HOST,
            'port': MYSQL_PORT,
            'user': MYSQL_USER,
            'passwd': MYSQL_PW
        },
        server_id=10, # arbitrary
        # only care about this database currently
        only_schemas=[NT_DB],
        # these tables in the database
        only_tables=["nyaa_torrents", "nyaa_statistics", "sukebei_torrents", "sukebei_statistics"],
        # from our save file
        resume_stream=True,
        log_file=pos['log_file'],
        log_pos=pos['log_pos'],
        # skip the other stuff like table mapping
        only_events=[UpdateRowsEvent, DeleteRowsEvent, WriteRowsEvent],
        # if we're at the head of the log, block until something happens
        # note it'd be nice to block async-style instead, but the mainline
        # binlogreader is synchronous. there is an (unmaintained?) fork
        # using aiomysql if anybody wants to revive that.
        blocking=True)

def reindex_torrent(t, index_name):
    # XXX annoyingly different from import_to_es, and
    # you need to keep them in sync manually.
    f = t['flags']
    doc = {
        "id": t['id'],
        "display_name": t['display_name'],
        "created_time": t['created_time'],
        "updated_time": t['updated_time'],
        "description": t['description'],
        # not analyzed but included so we can render magnet links
        # without querying sql again.
        "info_hash": t['info_hash'].hex(),
        "filesize": t['filesize'],
        "uploader_id": t['uploader_id'],
        "main_category_id": t['main_category_id'],
        "sub_category_id": t['sub_category_id'],
        # XXX all the bitflags are numbers
        "anonymous": bool(f & TorrentFlags.ANONYMOUS),
        "trusted": bool(f & TorrentFlags.TRUSTED),
        "remake": bool(f & TorrentFlags.REMAKE),
        "complete": bool(f & TorrentFlags.COMPLETE),
        # TODO instead of indexing and filtering later
        # could delete from es entirely. Probably won't matter
        # for at least a few months.
        "hidden": bool(f & TorrentFlags.HIDDEN),
        "deleted": bool(f & TorrentFlags.DELETED),
        "has_torrent": bool(t['has_torrent']),
    }
    # update, so we don't delete the stats if present
    es.update(
        index=index_name,
        doc_type='torrent',
        id=t['id'],
        body={"doc": doc, "doc_as_upsert": True})

def reindex_stats(s, index_name):
    es.update(
        index=index_name,
        doc_type='torrent',
        id=s['torrent_id'],
        body={
            "doc": {
                "stats_last_updated": s["last_updated"],
                "download_count": s["download_count"],
                "leech_count": s['leech_count'],
                "seed_count": s['seed_count'],
            }})

n = 0
last_save = time.time()

for event in stream:
    for row in event.rows:
        if event.table == "nyaa_torrents" or event.table == "sukebei_torrents":
            if event.table == "nyaa_torrents":
                index_name = "nyaa"
            else:
                index_name = "sukebei"
            if type(event) is WriteRowsEvent:
                reindex_torrent(row['values'], index_name)
            elif type(event) is UpdateRowsEvent:
                reindex_torrent(row['after_values'], index_name)
            elif type(event) is DeleteRowsEvent:
                # just delete it
                es.delete(index=index_name, doc_type='torrent', id=row['values']['id'])
            else:
                raise Exception(f"unknown event {type(event)}")
        elif event.table == "nyaa_statistics" or event.table == "sukebei_statistics":
            if event.table == "nyaa_torrents":
                index_name = "nyaa"
            else:
                index_name = "sukebei"
            if type(event) is WriteRowsEvent:
                reindex_stats(row['values'], index_name)
            elif type(event) is UpdateRowsEvent:
                reindex_stats(row['after_values'], index_name)
            elif type(event) is DeleteRowsEvent:
                # uh ok. assume that the torrent row will get deleted later.
                pass
            else:
                raise Exception(f"unknown event {type(event)}")
        else:
          raise Exception(f"unknown table {s.table}")
    n += 1
    if n % 100 == 0 or time.time() - last_save > 30:
        log.info(f"saving position {stream.log_file}/{stream.log_pos}")
        with open(SAVE_LOC, 'w') as f:
            json.dump({"log_file": stream.log_file, "log_pos": stream.log_pos}, f)

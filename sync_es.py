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

This uses multithreading so we don't have to block on socket io (both binlog
reading and es POSTing). asyncio soon™

This script will exit on any sort of exception, so you'll want to use your
supervisor's restart functionality, e.g. Restart=failure in systemd, or
the poor man's `while true; do sync_es.py; sleep 1; done` in tmux.
"""
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, BulkIndexError
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import UpdateRowsEvent, DeleteRowsEvent, WriteRowsEvent
from datetime import datetime

from nyaa import create_app, db, models
from nyaa.models import TorrentFlags
app = create_app('config')

import sys
import json
import time
import logging
from statsd import StatsClient
from threading import Thread
from queue import Queue, Empty

logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s - %(message)s')

log = logging.getLogger('sync_es')
log.setLevel(logging.INFO)

# config in json, 2lazy to argparse
if len(sys.argv) != 2:
    print("need config.json location", file=sys.stderr)
    sys.exit(-1)
with open(sys.argv[1]) as f:
    config = json.load(f)

# goes to netdata or other statsd listener
stats = StatsClient('localhost', 8125, prefix="sync_es")

#logging.getLogger('elasticsearch').setLevel(logging.DEBUG)

# in prod want in /var/lib somewhere probably
SAVE_LOC = config.get('save_loc', "/tmp/pos.json")
MYSQL_HOST = config.get('mysql_host', '127.0.0.1')
MYSQL_PORT = config.get('mysql_port', 3306)
MYSQL_USER = config.get('mysql_user', 'root')
MYSQL_PW = config.get('mysql_password', 'dunnolol')
NT_DB = config.get('database', 'nyaav2')
INTERNAL_QUEUE_DEPTH = config.get('internal_queue_depth', 10000)
ES_CHUNK_SIZE = config.get('es_chunk_size', 10000)
# seconds since no events happening to flush to es. remember this also
# interacts with es' refresh_interval setting.
FLUSH_INTERVAL = config.get('flush_interval', 5)

def pad_bytes(in_bytes, size):
    return in_bytes + (b'\x00' * max(0, size - len(in_bytes)))

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
        "info_hash": pad_bytes(t['info_hash'], 20).hex(),
        "filesize": t['filesize'],
        "uploader_id": t['uploader_id'],
        "main_category_id": t['main_category_id'],
        "sub_category_id": t['sub_category_id'],
        "comment_count": t['comment_count'],
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
    return {
        '_op_type': 'update',
        '_index': index_name,
        '_id': str(t['id']),
        "doc": doc,
        "doc_as_upsert": True
    }

def reindex_stats(s, index_name):
    # update the torrent at torrent_id, assumed to exist;
    # this will always be the case if you're reading the binlog
    # in order; the foreign key constraint on torrent_id prevents
    # the stats row from existing if the torrent isn't around.
    return {
        '_op_type': 'update',
        '_index': index_name,
        '_id': str(s['torrent_id']),
        "doc": {
            "stats_last_updated": s["last_updated"],
            "download_count": s["download_count"],
            "leech_count": s['leech_count'],
            "seed_count": s['seed_count'],
        }}

def delet_this(row, index_name):
    return {
        "_op_type": 'delete',
        '_index': index_name,
        '_id': str(row['values']['id'])}

# we could try to make this script robust to errors from es or mysql, but since
# the only thing we can do is "clear state and retry", it's easier to leave
# this to the supervisor. If we we carrying around heavier state in-process,
# it'd be more worth it to handle errors ourselves.
# 
# Apparently there's no setDefaultUncaughtExceptionHandler in threading, and
# sys.excepthook is also broken, so this gives us the same
# exit-if-anything-happens semantics. 
class ExitingThread(Thread):
    def run(self):
        try:
            self.run_happy()
        except:
            log.exception("something happened")
            # sys.exit only exits the thread, lame
            import os
            os._exit(1)

class BinlogReader(ExitingThread):
    # write_buf is the Queue we communicate with
    def __init__(self, write_buf):
        Thread.__init__(self)
        self.write_buf = write_buf

    def run_happy(self):
        with open(SAVE_LOC) as f:
            pos = json.load(f)

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

        log.info(f"reading binlog from {stream.log_file}/{stream.log_pos}")

        for event in stream:
            # save the pos of the stream and timestamp with each message, so we
            # can commit in the other thread. and keep track of process latency
            pos = (stream.log_file, stream.log_pos, event.timestamp)
            with stats.pipeline() as s:
                s.incr('total_events')
                s.incr(f"event.{event.table}.{type(event).__name__}")
                s.incr('total_rows', len(event.rows))
                s.incr(f"rows.{event.table}.{type(event).__name__}", len(event.rows))
                # XXX not a "timer", but we get a histogram out of it
                s.timing(f"rows_per_event.{event.table}.{type(event).__name__}", len(event.rows))

            if event.table == "nyaa_torrents" or event.table == "sukebei_torrents":
                if event.table == "nyaa_torrents":
                    index_name = "nyaa"
                else:
                    index_name = "sukebei"
                if type(event) is WriteRowsEvent:
                    for row in event.rows:
                        self.write_buf.put(
                                (pos, reindex_torrent(row['values'], index_name)),
                                block=True)
                elif type(event) is UpdateRowsEvent:
                    # UpdateRowsEvent includes the old values too, but we don't care
                    for row in event.rows:
                        self.write_buf.put(
                                (pos, reindex_torrent(row['after_values'], index_name)),
                                block=True)
                elif type(event) is DeleteRowsEvent:
                    # ok, bye
                    for row in event.rows:
                        self.write_buf.put((pos, delet_this(row, index_name)), block=True)
                else:
                    raise Exception(f"unknown event {type(event)}")
            elif event.table == "nyaa_statistics" or event.table == "sukebei_statistics":
                if event.table == "nyaa_statistics":
                    index_name = "nyaa"
                else:
                    index_name = "sukebei"
                if type(event) is WriteRowsEvent:
                    for row in event.rows:
                        self.write_buf.put(
                                (pos, reindex_stats(row['values'], index_name)),
                                block=True)
                elif type(event) is UpdateRowsEvent:
                    for row in event.rows:
                        self.write_buf.put(
                                (pos, reindex_stats(row['after_values'], index_name)),
                                block=True)
                elif type(event) is DeleteRowsEvent:
                    # uh ok. Assume that the torrent row will get deleted later,
                    # which will clean up the entire es "torrent" document
                    pass
                else:
                    raise Exception(f"unknown event {type(event)}")
            else:
              raise Exception(f"unknown table {s.table}")

class EsPoster(ExitingThread):
    # read_buf is the queue of stuff to bulk post
    def __init__(self, read_buf, chunk_size=1000, flush_interval=5):
        Thread.__init__(self)
        self.read_buf = read_buf
        self.chunk_size = chunk_size
        self.flush_interval = flush_interval

    def run_happy(self):
        es = Elasticsearch(hosts=app.config['ES_HOSTS'], timeout=30)

        last_save = time.time()
        since_last = 0
        # XXX keep track of last posted position for save points, awkward
        posted_log_file = None
        posted_log_pos = None

        while True:
            actions = []
            now = time.time()
            # wait up to flush_interval seconds after starting the batch
            deadline = now + self.flush_interval
            while len(actions) < self.chunk_size and now < deadline:
                timeout = deadline - now
                try:
                    # grab next event from queue with metadata that creepily
                    # updates, surviving outside the scope of the loop
                    ((log_file, log_pos, timestamp), action) = \
                            self.read_buf.get(block=True, timeout=timeout)
                    actions.append(action)
                    now = time.time()
                except Empty:
                    # nothing new for the whole interval
                    break

            if actions:
                # XXX "time" to get histogram of no events per bulk
                stats.timing('actions_per_bulk', len(actions))

                try:
                    with stats.timer('post_bulk'):
                        bulk(es, actions, chunk_size=self.chunk_size)
                except BulkIndexError as bie:
                     # in certain cases where we're really out of sync, we update a
                     # stat when the torrent doc is, causing a "document missing"
                     # error from es, with no way to suppress that server-side.
                     # Thus ignore that type of error if it's the only problem
                    for e in bie.errors:
                        try:
                            if e['update']['error']['type'] != 'document_missing_exception':
                                raise bie
                        except KeyError:
                            raise bie

                # how far we've gotten in the actual log
                posted_log_file = log_file
                posted_log_pos = log_pos

                # how far we're behind, wall clock
                stats.gauge('process_latency', int((time.time() - timestamp) * 1000))
            else:
                log.debug("no changes...")

            since_last += len(actions)
            # TODO instead of this manual timeout loop, could move this to another queue/thread
            if posted_log_file is not None and (since_last >= 10000 or (time.time() - last_save) > 10):
                log.info(f"saving position {log_file}/{log_pos}, {time.time() - timestamp:,.3f} seconds behind")
                with stats.timer('save_pos'):
                    with open(SAVE_LOC, 'w') as f:
                        json.dump({"log_file": posted_log_file, "log_pos": posted_log_pos}, f)
                last_save = time.time()
                since_last = 0
                posted_log_file = None
                posted_log_pos = None

# in-memory queue between binlog and es. The bigger it is, the more events we
# can parse in memory while waiting for es to catch up, at the expense of heap.
buf = Queue(maxsize=INTERNAL_QUEUE_DEPTH)

reader = BinlogReader(buf)
reader.daemon = True
writer = EsPoster(buf, chunk_size=ES_CHUNK_SIZE, flush_interval=FLUSH_INTERVAL)
writer.daemon = True
reader.start()
writer.start()

# on the main thread, poll the queue size for monitoring
while True:
    stats.gauge('queue_depth', buf.qsize())
    time.sleep(1)

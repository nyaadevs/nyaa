#!/usr/bin/python
import os
import sys

import MySQLdb
import MySQLdb.cursors

if len(sys.argv) != 3:
    print("Usage: {0} <prefix(nyaa|sukebei)> <outdir(info_dicts)>".format(sys.argv[0]))
    sys.exit(1)

prefix = sys.argv[1]
outdir = sys.argv[2]
if not os.path.exists(outdir):
    os.makedirs(outdir)


db = MySQLdb.connect(host='localhost',
                     user='test',
                     passwd='test123',
                     db='nyaav2',
                     cursorclass=MySQLdb.cursors.SSCursor)
cur = db.cursor()

cur.execute(
    """SELECT
            id,
            info_hash,
            info_dict
        FROM
            {0}_torrents
        JOIN {0}_torrents_info ON torrent_id = id
    """.format(prefix))

for row in cur:
    id = row[0]
    info_hash = row[1].hex().lower()
    info_dict = row[2]

    path = os.path.join(outdir, info_hash[0:2], info_hash[2:4])
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, info_hash)

    with open(path, 'wb') as fp:
        fp.write(info_dict)

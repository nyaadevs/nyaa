#!/bin/bash

# set +x

pushd /nyaa

echo 'Waiting for MySQL to start up'
while ! echo HELO | nc mariadb 3306 &>/dev/null; do
	sleep 1
done
echo 'DONE'

echo 'Waiting for ES to start up'
while ! echo HELO | nc elasticsearch 9200 &>/dev/null; do
	sleep 1
done
echo 'DONE'

echo 'Waiting for ES to be ready'
while ! curl -s -XGET 'elasticsearch:9200/_cluster/health?pretty=true&wait_for_status=green' &>/dev/null; do
	sleep 1
done
echo 'DONE'

echo 'Waiting for sync data file to exist'
while ! [ -f /elasticsearch-sync/pos.json ]; do
	sleep 1
done
echo 'DONE'

echo 'Starting the sync process'
/usr/bin/python3 /nyaa/sync_es.py /nyaa/.docker/es_sync_config.json

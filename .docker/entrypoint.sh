#!/bin/bash

# set +x

pushd /nyaa

echo 'Waiting for MySQL to start up'
while ! echo HELO | nc mariadb 3306 &>/dev/null; do
	sleep 1
done
echo 'DONE'

if ! [ -f /elasticsearch-sync/flag-db_create ]; then
	python3 ./db_create.py
	touch /elasticsearch-sync/flag-db_create
fi

if ! [ -f /elasticsearch-sync/flag-db_migrate ]; then
	python3 ./db_migrate.py stamp head
	touch /elasticsearch-sync/flag-db_migrate
fi

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

if ! [ -f /elasticsearch-sync/flag-create_es ]; then
	# @source create_es.sh
	# create indices named "nyaa" and "sukebei", these are hardcoded
	curl -v -XPUT 'elasticsearch:9200/nyaa?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
	curl -v -XPUT 'elasticsearch:9200/sukebei?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
	touch /elasticsearch-sync/flag-create_es
fi

if ! [ -f /elasticsearch-sync/flag-import_to_es ]; then
	python3 ./import_to_es.py | tee /elasticsearch-sync/import.out
	grep -A1 'Save the following' /elasticsearch-sync/import.out | tail -1 > /elasticsearch-sync/pos.json
	touch /elasticsearch-sync/flag-import_to_es
fi

echo 'Starting the Flask app'
/usr/local/bin/uwsgi /nyaa/.docker/uwsgi.config.ini

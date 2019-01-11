#!/bin/bash

# set +x

pushd /nyaa

echo 'Waiting for MySQL to start up'
while ! echo HELO | nc mariadb 3306; do
	echo -n '.'
	sleep 1
done
echo 'DONE'

if ! [ -f /tmp/flag-db_create ]; then
	python3 ./db_create.py
	touch /tmp/flag-db_create
fi

if ! [ -f /tmp/flag-db_migrate ]; then
	python3 ./db_migrate.py stamp head
	touch /tmp/flag-db_migrate
fi

echo 'Waiting for ES to start up'
while ! echo HELO | nc elasticsearch 9200; do
	echo -n '.'
	sleep 1
done
echo 'DONE'

if ! [ -f /tmp/flag-create_es ]; then
	# @source create_es.sh
	# create indices named "nyaa" and "sukebei", these are hardcoded
	curl -v -XPUT 'elasticsearch:9200/nyaa?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
	curl -v -XPUT 'elasticsearch:9200/sukebei?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
	touch /tmp/flag-create_es
fi

if ! [ -f /tmp/flag-import_to_es ]; then
	python3 ./import_to_es.py
	touch /tmp/flag-import_to_es
fi

echo 'Starting the Flask app'
python3 WSGI.py

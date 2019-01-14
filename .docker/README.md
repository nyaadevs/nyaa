# Nyaa on Docker

Docker infrastructure is provided to ease setting up a dev environment

## Quickstart

Get started by running (from the root of the project):

	docker-compose -f .docker/full-stack.yml -p nyaa build nyaa-flask
	docker-compose -f .docker/full-stack.yml -p nyaa up -d

This builds the Flask app container, then starts up the project. You can then go
to [localhost:8080](http://localhost:8080/) (note that some of the
services are somewhat slow to start so it may not be available for 30s or so).

You can shut it down with:

	docker-compose -f .docker/full-stack.yml -p nyaa down

## Details

The environment includes:
  - [nginx frontend](http://localhost:8080/) (on port 8080)
  - uwsgi running the flask app
  - the ES<>MariaDB sync process
  - MariaDB
  - ElasticSearch
  - [Kibana](http://localhost:8080/kibana/) (at /kibana/)

MariaDB, ElasticSearch, the sync process, and uploaded torrents will
persistently store their data in volumes which makes future start ups faster.

To make it more useful to develop with, you can copy `.docker/full-stack.yml` and
edit the copy and uncomment the `- "${NYAA_SRC_DIR}:/nyaa"` line, then
`export NYAA_SRC_DIR=$(pwd)` and start up the environment using the new compose
file:

	cp -a .docker/full-stack.yml .docker/local-dev.yml
	cat config.example.py .docker/nyaa-config-partial.py > ./config.py
	$EDITOR .docker/local-dev.yml
	export NYAA_SRC_DIR=$(pwd)
	docker-compose -f .docker/local-dev.yml -p nyaa up -d

This will mount the local copy of the project files into the Flask container,
which combined with live-reloading in uWSGI should let you make changes and see
them take effect immediately (technically with a ~2 second delay).

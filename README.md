# NyaaV2

## Setup:

- Create your virtualenv, for example with `pyvenv venv`
- Enter your virtualenv with `source venv/bin/activate`
- Install dependencies with `pip install -r requirements.txt`
- Run `python db_create.py` to create the database
- Start the dev server with `python run.py`

## Updated Setup (python 3.6.1):

- Install dependencies https://github.com/pyenv/pyenv/wiki/Common-build-problems
- Install `pyenv` https://github.com/pyenv/pyenv/blob/master/README.md#installation
- Install `pyenv-virtualenv` https://github.com/pyenv/pyenv-virtualenv/blob/master/README.md
- `pyenv install 3.6.1`
- `pyenv virtualenv 3.6.1 nyaa`
- `pyenv activate nyaa`
- Install dependencies with `pip install -r requirements.txt`
- Copy `config.example.py` into `config.py`
- Change TABLE_PREFIX to `nyaa_` or `sukebei_` depending on the site

## Setting up MySQL/MariaDB database for advanced functionality
- Enable `USE_MYSQL` flag in config.py
- Install latest mariadb by following instructions here https://downloads.mariadb.org/mariadb/repositories/
    - Tested versions: `mysql  Ver 15.1 Distrib 10.0.30-MariaDB, for debian-linux-gnu (x86_64) using readline 5.2`
- Run the following commands logged in as your root db user:
    - `CREATE USER 'test'@'localhost' IDENTIFIED BY 'test123';`
    - `GRANT ALL PRIVILEGES ON * . * TO 'test'@'localhost';`
    - `FLUSH PRIVILEGES;`
    - `CREATE DATABASE nyaav2 DEFAULT CHARACTER SET utf8 COLLATE utf8_bin;`
- To setup and import nyaa_maria_vx.sql:
    - `mysql -u <user> -p nyaav2`
    - `DROP DATABASE nyaav2;`
    - `CREATE DATABASE nyaav2 DEFAULT CHARACTER SET utf8 COLLATE utf8_bin;`
    - `SOURCE ~/path/to/database/nyaa_maria_vx.sql`

## Finishing up
- Run `python db_create.py` to create the database
- Load the .sql file
    - `mysql -u user -p nyaav2`
    - `SOURCE cocks.sql`
    - Remember to change the default user password to an empty string to disable logging in
- Start the dev server with `python run.py`
- Deactivate `source deactivate`

# Enabling ElasticSearch

## Basics
- Install jdk `sudo apt-get install openjdk-8-jdk`
- Install elasticsearch https://www.elastic.co/guide/en/elasticsearch/reference/current/deb.html
- `sudo systemctl enable elasticsearch.service`
- `sudo systemctl start elasticsearch.service`
- Run `curl -XGET 'localhost:9200'` and make sure ES is running
- Optional: install Kabana as a search frontend for ES

## Enable MySQL Binlogging
- Add the `[mariadb]` bin-log section to my.cnf and reload mysql server
- Connect to mysql
- `SHOW VARIABLES LIKE 'binlog_format';`
    - Make sure it shows ROW
- Connect to root user
- `GRANT REPLICATION SLAVE ON *.* TO 'test'@'localhost';` where test is the user you will be running `sync_es.py` with

## Setting up ES
- Run `./create_es.sh` and this creates two indicies: `nyaa` and `sukebei`
- The output should show `acknowledged: true` twice
- The safest bet is to disable the webapp here to ensure there's no database writes
- Run `python import_to_es.py` with `SITE_FLAVOR` set to `nyaa`
- Run `python import_to_es.py` with `SITE_FLAVOR` set to `sukebei`
- These will take some time to run as it's indexing

## Setting up sync_es.py
- Sync_es.py keeps the ElasticSearch index updated by reading the BinLog
- Configure the MySQL options with the user where you granted the REPLICATION permissions
- Connect to MySQL, run `SHOW MASTER STATUS;`.
- Copy the output to `/var/lib/sync_es_position.json` with the contents `{"log_file": "FILE", "log_pos": POSITION}` and replace FILENAME with File (something like master1-bin.000002) in the SQL output and POSITION (something like 892528513) with Position
- Set up `sync_es.py` as a service and run it, preferably as the system/root
- Make sure `sync_es.py` runs within venv with the right dependencies

## Database migrations
- Uses [flask-Migrate](https://flask-migrate.readthedocs.io/)
- Run `./db_migrate.py db migrate` to generate the migration script after database model changes.
- Take a look at the result in `migrations/versions/...` to make sure nothing went wrong.
- Run `./db_migrate.py db upgrade` to upgrade your database.

## Good to go!
- After that, enable the `USE_ELASTIC_SEARCH` flag and restart the webapp and you're good to go


## Code Quality:
- Remember to follow PEP8 style guidelines and run `./lint.sh` before committing.

#!/usr/bin/python3
# -*- coding: utf-8 -*-
from nyaa import app, db
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand

migrate = Migrate(app, db)

manager = Manager(app)
manager.add_command("db", MigrateCommand)

if __name__ == "__main__":
	manager.run()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from nyaa import app, db
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand

migrate = Migrate(app, db)

manager = Manager(app)
manager.add_command("db", MigrateCommand)

if __name__ == "__main__":
	# Patch sys.argv to default to 'db'
	argv_contents = sys.argv[:]
	
	sys.argv.clear()
	sys.argv.append(argv_contents[0])
	sys.argv.append('db')
	sys.argv.extend(argv_contents[1:])

	manager.run()

import os
import os.path as op
import unittest

from nyaa import create_app


class CustomConfig(object):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = '***'  # For DebugToolbar
    LOG_FILE = op.abspath(op.join(op.dirname(__file__), 'test.log'))


class TestAppFactory(unittest.TestCase):
    def setUp(self):
        if op.isfile(CustomConfig.LOG_FILE):
            os.remove(CustomConfig.LOG_FILE)

    def test_create_app(self):
        # config is usually a class or a module
        app = create_app(config=CustomConfig)

        self.assertIn('DEBUG', app.config)
        self.assertTrue(app.config['DEBUG'])

        del app


if __name__ == '__main__':
    unittest.main()

""" Sets up helper class for testing """

import os
import unittest

from nyaa import create_app

USE_MYSQL = True


class NyaaTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app = create_app('config')
        app.config['TESTING'] = True
        cls.app_context = app.app_context()

        # Use a separate database for testing
        # if USE_MYSQL:
        #     cls.db_name = 'nyaav2_tests'
        #     db_uri = 'mysql://root:@localhost/{}?charset=utf8mb4'.format(cls.db_name)
        # else:
        #     cls.db_name = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'test.db')
        #     db_uri = 'sqlite:///{}?check_same_thread=False'.format(cls.db_name)

        # if not os.environ.get('TRAVIS'):  # Travis doesn't need a separate DB
        #     app.config['USE_MYSQL'] = USE_MYSQL
        #     app.config['SQLALCHEMY_DATABASE_URI'] = db_uri

        with cls.app_context:
            cls.app = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app_context:
            pass

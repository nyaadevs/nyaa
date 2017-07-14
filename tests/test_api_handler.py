import unittest
import json

from nyaa import api_handler, models
from tests import NyaaTestCase
from pprint import pprint


class ApiHandlerTests(NyaaTestCase):

    # @classmethod
    # def setUpClass(cls):
    #     super(ApiHandlerTests, cls).setUpClass()

    # @classmethod
    # def tearDownClass(cls):
    #     super(ApiHandlerTests, cls).tearDownClass()

    def test_no_authorization(self):
        """ Test that API is locked unless you're logged in """
        rv = self.client.get('/api/info/1')
        data = json.loads(rv.get_data())
        self.assertDictEqual({'errors': ['Bad authorization']}, data)

    @unittest.skip('Not yet implemented')
    def test_bad_credentials(self):
        """ Test that API is locked unless you're logged in """
        rv = self.client.get('/api/info/1')
        data = json.loads(rv.get_data())
        self.assertDictEqual({'errors': ['Bad authorization']}, data)


if __name__ == '__main__':
    unittest.main()

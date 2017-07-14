import unittest

from tests import NyaaTestCase


class SiteTestCase(NyaaTestCase):
    """ Tests for nyaa.views.site """
    # def test_about_url(self):
    #     rv = self.client.get('/about')
    #     self.assertIn(b'About', rv.data)

    def test_rules_url(self):
        rv = self.client.get('/rules')
        self.assertIn(b'Site Rules', rv.data)

    def test_help_url(self):
        rv = self.client.get('/help')
        self.assertIn(b'Using the Site', rv.data)

    def test_xmlns_url(self):
        rv = self.client.get('/xmlns/nyaa')
        self.assertIn(b'Nyaa XML Namespace', rv.data)


if __name__ == '__main__':
    unittest.main()

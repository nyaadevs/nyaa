import unittest

from tests import NyaaTestCase


class MainTestCase(NyaaTestCase):
    """ Tests for nyaa.views.main """
    def test_index_url(self):
        rv = self.client.get('/')
        self.assertIn(b'Browse :: Nyaa', rv.data)
        self.assertIn(b'Guest', rv.data)

    def test_rss_url(self):
        rv = self.client.get('/?page=rss')
        self.assertIn(b'/xmlns/nyaa', rv.data)

    def test_invalid_url(self):
        rv = self.client.get('/notarealpage')
        self.assertIn(b'404 Not Found', rv.data)


if __name__ == '__main__':
    unittest.main()

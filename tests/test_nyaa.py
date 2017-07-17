import os
import unittest
import tempfile
import nyaa


class NyaaTestCase(unittest.TestCase):

    nyaa_app = nyaa.create_app('config')

    def setUp(self):
        self.db, self.nyaa_app.config['DATABASE'] = tempfile.mkstemp()
        self.nyaa_app.config['TESTING'] = True
        self.app = self.nyaa_app.test_client()
        with self.nyaa_app.app_context():
            nyaa.db.create_all()

    def tearDown(self):
        os.close(self.db)
        os.unlink(self.nyaa_app.config['DATABASE'])

    def test_index_url(self):
        rv = self.app.get('/')
        assert b'Browse :: Nyaa' in rv.data
        assert b'Guest' in rv.data

    def test_upload_url(self):
        rv = self.app.get('/upload')
        assert b'Upload Torrent' in rv.data
        assert b'You are not logged in, and are uploading anonymously.' in rv.data

    def test_rules_url(self):
        rv = self.app.get('/rules')
        assert b'Site Rules' in rv.data

    def test_help_url(self):
        rv = self.app.get('/help')
        assert b'Using the Site' in rv.data

    def test_rss_url(self):
        rv = self.app.get('/?page=rss')
        assert b'/xmlns/nyaa' in rv.data

    def test_login_url(self):
        rv = self.app.get('/login')
        assert b'Username or email address' in rv.data

    def test_registration_url(self):
        rv = self.app.get('/register')
        assert b'Username' in rv.data
        assert b'Password' in rv.data


if __name__ == '__main__':
    unittest.main()

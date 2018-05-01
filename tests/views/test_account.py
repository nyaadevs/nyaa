import unittest

from tests import NyaaTestCase


class AccountTestCase(NyaaTestCase):
    """ Tests for nyaa.views.account """
    def test_login(self):
        rv = self.client.get('/login')
        self.assertIn(b'Username or email address', rv.data)

    def test_logout(self):
        rv = self.client.get('/logout')
        self.assertIn(b'Redirecting...', rv.data)

    def test_register(self):
        rv = self.client.get('/register')
        self.assertIn(b'Username', rv.data)
        self.assertIn(b'Password', rv.data)

    @unittest.skip('Not yet implemented')
    def test_profile(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_redirect_url(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_send_verification_email(self):
        pass


if __name__ == '__main__':
    unittest.main()

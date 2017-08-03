import unittest
from hashlib import md5
from urllib.parse import urlencode

import flask

from tests import NyaaTestCase
from nyaa import models


class TestUserModel(NyaaTestCase):
    def setUp(self):
        self.user = models.User(username='test_user', email='user@test.com', password='passwd_hash')

    def test_basic(self):
        """ Test basic attributes """
        self.assertEqual(repr(self.user), '<User \'test_user\'>')
        self.assertEqual(self.user.username, 'test_user')
        self.assertEqual(self.user.email, 'user@test.com')
        # expected failure
        # self.assertEqual(self.user.password_hash, 'passwd_hash')
        self.assertEqual(self.user.status, models.UserStatusType.INACTIVE)
        self.assertEqual(self.user.level, models.UserLevelType.REGULAR)

    def test_userlevel_str(self):
        """ Test user level strings and colors """
        self.user.level = models.UserLevelType.REGULAR
        self.assertEqual(self.user.userlevel_str, 'User')
        self.assertEqual(self.user.userlevel_color, 'default')

        self.user.level = models.UserLevelType.TRUSTED
        self.assertEqual(self.user.userlevel_str, 'Trusted')
        self.assertEqual(self.user.userlevel_color, 'success')

        self.user.level = models.UserLevelType.MODERATOR
        self.assertEqual(self.user.userlevel_str, 'Moderator')
        self.assertEqual(self.user.userlevel_color, 'purple')

        # Superadmins also show up as Moderators
        self.user.level = models.UserLevelType.SUPERADMIN
        self.assertEqual(self.user.userlevel_str, 'Moderator')
        self.assertEqual(self.user.userlevel_color, 'purple')

    def test_userstatus_str(self):
        """ Test user status strings """
        self.user.status = models.UserStatusType.INACTIVE
        self.assertEqual(self.user.userstatus_str, 'Inactive')
        self.user.status = models.UserStatusType.ACTIVE
        self.assertEqual(self.user.userstatus_str, 'Active')
        self.user.status = models.UserStatusType.BANNED
        self.assertEqual(self.user.userstatus_str, 'Banned')

    def test_is_x_properties(self):
        """ Test user.is_x properties """
        self.user.status = models.UserStatusType.BANNED
        self.assertTrue(self.user.is_banned)
        self.assertFalse(self.user.is_trusted)
        self.assertFalse(self.user.is_moderator)
        self.assertFalse(self.user.is_superadmin)
        self.user.status = models.UserStatusType.INACTIVE

        self.user.level = models.UserLevelType.REGULAR
        self.assertFalse(self.user.is_banned)
        self.assertFalse(self.user.is_trusted)
        self.assertFalse(self.user.is_moderator)
        self.assertFalse(self.user.is_superadmin)

        self.user.level = models.UserLevelType.TRUSTED
        self.assertFalse(self.user.is_banned)
        self.assertTrue(self.user.is_trusted)
        self.assertFalse(self.user.is_moderator)
        self.assertFalse(self.user.is_superadmin)

        # Moderators and above are also trusted
        self.user.level = models.UserLevelType.MODERATOR
        self.assertFalse(self.user.is_banned)
        self.assertTrue(self.user.is_trusted)
        self.assertTrue(self.user.is_moderator)
        self.assertFalse(self.user.is_superadmin)

        # Superadmins also show up as Moderators
        self.user.level = models.UserLevelType.SUPERADMIN
        self.assertFalse(self.user.is_banned)
        self.assertTrue(self.user.is_trusted)
        self.assertTrue(self.user.is_moderator)
        self.assertTrue(self.user.is_superadmin)

    def test_gravatar_url(self):
        """ Test user Gravatar URL """
        with self.request_context():
            expected_gravatar_url = 'https://www.gravatar.com/avatar/{email_hash}?{params}'.format(
                email_hash=md5(self.user.email.encode('utf-8').lower()).hexdigest(),
                params=urlencode({
                    's': 120,
                    'd': flask.url_for('static', filename='img/avatar/default.png', _external=True),
                    'r': 'pg' if self.app.config['SITE_FLAVOR'] == 'nyaa' else 'x',
                })
            )
            self.assertEqual(self.user.gravatar_url(), expected_gravatar_url)


if __name__ == '__main__':
    unittest.main()

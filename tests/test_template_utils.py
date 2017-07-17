import datetime
import os.path
import posixpath
import unittest
from email.utils import formatdate

from tests import NyaaTestCase
from nyaa.template_utils import (_jinja2_filter_rfc822, _jinja2_filter_rfc822_es, get_utc_timestamp,
                                 get_display_time, timesince, filter_truthy, category_name,
                                 static_cachebuster, _static_cache)


class TestTemplateUtils(NyaaTestCase):

    @unittest.skip('Not yet implemented')
    def test_create_magnet_from_es_info(self):
        pass

    def test_static_cachebuster(self):
        with self.request_context:
            # Save this value in order to restore it in the end.
            orig_debug = self.app.debug

            static_file = 'js/main.js'
            static_url = posixpath.join(self.app.static_url_path, static_file)

            # Test no cache-busting (disabled on debug = True)
            self.app.debug = True
            self.assertEqual(static_cachebuster(static_file), static_url)

            # Test actual cache-busting
            self.app.debug = False
            static_file_path = os.path.abspath(os.path.join(self.app.static_folder, static_file))
            modified = int(os.path.getmtime(static_file_path))

            self.assertEqual(static_cachebuster(static_file),
                             '{0}?t={1}'.format(static_url, modified))
            self.assertEqual(_static_cache.get(static_file), modified)

            # Test a static file that doesn't exist
            self.assertEqual(static_cachebuster('notarealfile.ext'),
                             posixpath.join(self.app.static_url_path, 'notarealfile.ext'))

            self.app.debug = orig_debug

    @unittest.skip('Not yet implemented')
    def test_modify_query(self):
        pass

    def test_filter_truthy(self):
        my_list = [
            True, False,  # booleans
            'hello!', '',  # strings
            1, 0, -1,  # integers
            1.0, 0.0, -1.0,  # floats
            ['test'], [],  # lists
            {'marco': 'polo'}, {},  # dictionaries
            None
        ]
        expected_result = [
            True,
            'hello!',
            1, -1,
            1.0, -1.0,
            ['test'],
            {'marco': 'polo'}
        ]
        self.assertListEqual(filter_truthy(my_list), expected_result)

    def test_category_name(self):
        with self.app_context:
            # Nyaa categories only
            self.assertEqual(category_name('1_0'), 'Anime')
            self.assertEqual(category_name('1_2'), 'Anime - English-translated')
            # Unknown category ids
            self.assertEqual(category_name('100_0'), '???')
            self.assertEqual(category_name('1_100'), '???')
            self.assertEqual(category_name('0_0'), '???')

    def test_get_utc_timestamp(self):
        # test with local timezone
        test_date_str = '2017-02-15T11:15:34'
        self.assertEqual(get_utc_timestamp(test_date_str), 1487157334)

    def test_get_display_time(self):
        # test with local timezone
        test_date_str = '2017-02-15T11:15:34'
        self.assertEqual(get_display_time(test_date_str), '2017-02-15 11:15')

    def test_filter_rfc822(self):
        # test with timezone UTC
        test_date = datetime.datetime(2017, 2, 15, 11, 15, 34, 100, datetime.timezone.utc)
        self.assertEqual(_jinja2_filter_rfc822(test_date), 'Wed, 15 Feb 2017 11:15:34 -0000')

    def test_filter_rfc822_es(self):
        # test with local timezone
        test_date_str = '2017-02-15T11:15:34'
        # this is in order to get around local time zone issues
        expected = formatdate(float(datetime.datetime(2017, 2, 15, 11, 15, 34, 100).timestamp()))
        self.assertEqual(_jinja2_filter_rfc822_es(test_date_str), expected)

    def test_timesince(self):
        now = datetime.datetime.utcnow()
        self.assertEqual(timesince(now), 'just now')
        self.assertEqual(timesince(now - datetime.timedelta(seconds=5)), '5 seconds ago')
        self.assertEqual(timesince(now - datetime.timedelta(minutes=1)), '1 minute ago')
        self.assertEqual(
            timesince(now - datetime.timedelta(minutes=38, seconds=43)), '38 minutes ago')
        self.assertEqual(
            timesince(now - datetime.timedelta(hours=2, minutes=38, seconds=51)), '2 hours ago')
        bigger = now - datetime.timedelta(days=3)
        self.assertEqual(timesince(bigger), bigger.strftime('%Y-%m-%d %H:%M UTC'))


if __name__ == '__main__':
    unittest.main()

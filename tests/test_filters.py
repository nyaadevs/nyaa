import unittest
import datetime

from email.utils import formatdate

from nyaa.routes import (_jinja2_filter_rfc822, _jinja2_filter_rfc822_es, get_utc_timestamp,
                         get_display_time, timesince)


class TestFilters(unittest.TestCase):

    # def setUp(self):
    #     self.db, nyaa.app.config['DATABASE'] = tempfile.mkstemp()
    #     nyaa.app.config['TESTING'] = True
    #     self.app = nyaa.app.test_client()
    #     with nyaa.app.app_context():
    #         nyaa.db.create_all()
    #
    # def tearDown(self):
    #     os.close(self.db)
    #     os.unlink(nyaa.app.config['DATABASE'])

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

    def test_get_utc_timestamp(self):
        # test with local timezone
        test_date_str = '2017-02-15T11:15:34'
        self.assertEqual(get_utc_timestamp(test_date_str), 1487157334)

    def test_get_display_time(self):
        # test with local timezone
        test_date_str = '2017-02-15T11:15:34'
        self.assertEqual(get_display_time(test_date_str), '2017-02-15 11:15')

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

    @unittest.skip('Not yet implemented')
    def test_static_cachebuster(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_modify_query(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_filter_truthy(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_category_name(self):
        pass


if __name__ == '__main__':
    unittest.main()

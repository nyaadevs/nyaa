import unittest

from tests import NyaaTestCase


class TorrentsTestCase(NyaaTestCase):
    """ Tests for nyaa.views.torrents """

    @unittest.skip('Not yet implemented')
    def test_view_url(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_edit_url(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_redirect_magnet(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_download_torrent(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_delete_comment(self):
        pass

    @unittest.skip('Not yet implemented')
    def test_submit_report(self):
        pass

    def test_upload_url(self):
        rv = self.client.get('/upload')
        self.assertIn(b'Upload Torrent', rv.data)
        self.assertIn(b'You are not logged in, and are uploading anonymously.', rv.data)

    @unittest.skip('Not yet implemented')
    def test__create_upload_category_choices(self):
        pass

    @unittest.skip('Not yet implemented')
    def test__get_cached_torrent_file(self):
        pass


if __name__ == '__main__':
    unittest.main()

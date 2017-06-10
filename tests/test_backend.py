import unittest

from nyaa import backend


class TestBackend(unittest.TestCase):

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

    def test_replace_utf8_values(self):
        test_dict = {
            'hash': '2346ad27d7568ba9896f1b7da6b5991251debdf2',
            'title.utf-8': '¡hola! ¿qué tal?',
            'filelist.utf-8': [
                'Español 101.mkv',
                'ру́сский 202.mp4'
            ]
        }
        expected_dict = {
            'hash': '2346ad27d7568ba9896f1b7da6b5991251debdf2',
            'title': '¡hola! ¿qué tal?',
            'filelist': [
                'Español 101.mkv',
                'ру́сский 202.mp4'
            ]
        }

        self.assertTrue(backend._replace_utf8_values(test_dict))
        self.assertDictEqual(test_dict, expected_dict)

    @unittest.skip('Not yet implemented')
    def test_handle_torrent_upload(self):
        pass


if __name__ == '__main__':
    unittest.main()

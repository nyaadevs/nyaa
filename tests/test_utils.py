import unittest
from collections import OrderedDict

from hashlib import sha1
from nyaa import utils


class TestUtils(unittest.TestCase):

    def test_sha1_hash(self):
        bencoded_test_data = b'd5:hello5:world7:numbersli1ei2eee'
        self.assertEqual(
            utils.sha1_hash(bencoded_test_data),
            sha1(bencoded_test_data).digest())

    def test_sorted_pathdict(self):
        initial = {
            'api_handler.py': 11805,
            'routes.py': 34247,
            '__init__.py': 6499,
            'torrents.py': 11948,
            'static': {
                'img': {
                    'nyaa.png': 1200,
                    'sukebei.png': 1100,
                },
                'js': {
                    'main.js': 3000,
                },
            },
            'search.py': 5148,
            'models.py': 24293,
            'templates': {
                'upload.html': 3000,
                'home.html': 1200,
                'layout.html': 23000,
            },
            'utils.py': 14700,
        }
        expected = OrderedDict({
            'static': OrderedDict({
                'img': OrderedDict({
                    'nyaa.png': 1200,
                    'sukebei.png': 1100,
                }),
                'js': OrderedDict({
                    'main.js': 3000,
                }),
            }),
            'templates': OrderedDict({
                'home.html': 1200,
                'layout.html': 23000,
                'upload.html': 3000,
            }),
            '__init__.py': 6499,
            'api_handler.py': 11805,
            'models.py': 24293,
            'routes.py': 34247,
            'search.py': 5148,
            'torrents.py': 11948,
            'utils.py': 14700,
        })
        self.assertDictEqual(utils.sorted_pathdict(initial), expected)

    @unittest.skip('Not yet implemented')
    def test_cached_function(self):
        # TODO: Test with a function that generates something random?
        pass

    def test_flatten_dict(self):
        initial = OrderedDict({
            'static': OrderedDict({
                'img': OrderedDict({
                    'nyaa.png': 1200,
                    'sukebei.png': 1100,
                }),
                'js': OrderedDict({
                    'main.js': 3000,
                }),
                'favicon.ico': 1000,
            }),
            'templates': [
                {'home.html': 1200},
                {'layout.html': 23000},
                {'upload.html': 3000},
            ],
            '__init__.py': 6499,
            'api_handler.py': 11805,
            'models.py': 24293,
            'routes.py': 34247,
            'search.py': 5148,
            'torrents.py': 11948,
            'utils.py': 14700,
        })
        expected = {
            'static/img/nyaa.png': 1200,
            'static/img/sukebei.png': 1100,
            'static/js/main.js': 3000,
            'static/favicon.ico': 1000,
            'templates/home.html': 1200,
            'templates/layout.html': 23000,
            'templates/upload.html': 3000,
            '__init__.py': 6499,
            'api_handler.py': 11805,
            'models.py': 24293,
            'routes.py': 34247,
            'search.py': 5148,
            'utils.py': 14700,
            'torrents.py': 11948,
        }
        self.assertDictEqual(utils.flatten_dict(initial), expected)


if __name__ == '__main__':
    unittest.main()

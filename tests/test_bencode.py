import unittest

from nyaa import bencode


class TestBencode(unittest.TestCase):

    def test_pairwise(self):
        # test list with even length
        initial = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        expected = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)]

        for index, values in enumerate(bencode._pairwise(initial)):
            self.assertEqual(values, expected[index])

        # test list with odd length
        initial = [0, 1, 2, 3, 4]
        expected = [(0, 1), (2, 3), 4]

        for index, values in enumerate(bencode._pairwise(initial)):
            self.assertEqual(values, expected[index])

        # test non-iterable
        initial = b'012345'
        expected = [(48, 49), (50, 51), (52, 53)]  # decimal ASCII
        for index, values in enumerate(bencode._pairwise(initial)):
            self.assertEqual(values, expected[index])

    def test_encode(self):
        exception_test_cases = [  # (raw, raised_exception, expected_result_regexp)
            # test unsupported type
            (None, bencode.BencodeException,
                r'Unsupported type'),
            (1.6, bencode.BencodeException,
                r'Unsupported type'),
        ]

        test_cases = [  # (raw, expected_result)
            (100, b'i100e'),  # int
            (-5, b'i-5e'),  # int
            ('test', b'4:test'),  # str
            (b'test', b'4:test'),  # byte
            (['test', 100], b'l4:testi100ee'),  # list
            ({'numbers': [1, 2], 'hello': 'world'}, b'd5:hello5:world7:numbersli1ei2eee')  # dict
        ]

        for raw, raised_exception, expected_result_regexp in exception_test_cases:
            self.assertRaisesRegexp(raised_exception, expected_result_regexp, bencode.encode, raw)

        for raw, expected_result in test_cases:
            self.assertEqual(bencode.encode(raw), expected_result)

    def test_decode(self):
        exception_test_cases = [  # (raw, raised_exception, expected_result_regexp)
            # test malformed bencode
            (b'l4:hey', bencode.MalformedBencodeException,
                r'Read only \d+ bytes, \d+ wanted'),
            (b'ie', bencode.MalformedBencodeException,
                r'Unable to parse int'),
            (b'i64', bencode.MalformedBencodeException,
                r'EOF, expecting more integer'),
            (b'', bencode.MalformedBencodeException,
                r'EOF, expecting kind'),
            (b'i6-4', bencode.MalformedBencodeException,
                r'Unexpected input while reading an integer'),
            (b'4#string', bencode.MalformedBencodeException,
                r'Unexpected input while reading string length'),
            (b'4', bencode.MalformedBencodeException,
                r'EOF, expecting more string len'),
            (b'$:string', bencode.MalformedBencodeException,
                r'Unexpected data type'),
            (b'd5:world7:numbersli1ei2eee', bencode.MalformedBencodeException,
                r'Uneven amount of key/value pairs'),
        ]

        test_cases = [  # (raw, expected_result)
            (b'i100e', 100),  # int
            (b'i-5e', -5),  # int
            ('4:test', b'test'),  # str
            (b'4:test', b'test'),  # byte
            (b'15:thisisalongone!', b'thisisalongone!'),  # big byte
            (b'l4:testi100ee', [b'test', 100]),  # list
            (b'd5:hello5:world7:numbersli1ei2eee', {'hello': b'world', 'numbers': [1, 2]})  # dict
        ]

        for raw, raised_exception, expected_result_regexp in exception_test_cases:
            self.assertRaisesRegexp(raised_exception, expected_result_regexp, bencode.decode, raw)

        for raw, expected_result in test_cases:
            self.assertEqual(bencode.decode(raw), expected_result)


if __name__ == '__main__':
    unittest.main()

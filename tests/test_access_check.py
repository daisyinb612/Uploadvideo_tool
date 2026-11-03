import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from services.access_check import open_public, verify_video


class PublicAccess(unittest.TestCase):
    def test_platform_uses_dedicated_opener_and_retries_network_failure(self):
        with patch('services.access_check.build_opener') as build, patch('services.access_check.time.sleep'):
            build.return_value.open.side_effect = [URLError('handshake timed out'), 'response']
            self.assertEqual(open_public('https://innojudge.ecnu.edu.cn/video.mp4'), 'response')
            self.assertEqual(build.return_value.open.call_count, 2)

    def test_missing_video_is_not_retried(self):
        with patch('services.access_check.build_opener') as build:
            build.return_value.open.side_effect = HTTPError('https://innojudge.ecnu.edu.cn/missing',404,'Missing',None,None)
            with self.assertRaises(HTTPError):
                open_public('https://innojudge.ecnu.edu.cn/missing')
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_content_and_size_must_match_export(self):
        response = MagicMock(status=206)
        response.headers = {'Content-Type':'video/mp4','Content-Range':'bytes 0-31/100'}
        response.read.return_value = b'\x00\x00\x00\x20ftypisom'
        response.__enter__.return_value = response
        with patch('services.access_check.open_public',return_value=response):
            self.assertTrue(verify_video('https://example.test/video',100)['accessible'])
            with self.assertRaisesRegex(ValueError,'大小'):
                verify_video('https://example.test/video',200)
            response.read.return_value = b'<html>error</html>'
            with self.assertRaisesRegex(ValueError,'MP4'):
                verify_video('https://example.test/video',100)

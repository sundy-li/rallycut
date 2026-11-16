import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import download_model
from pretrained import WEIGHTS_SHA256, WEIGHTS_URL

MANIFEST = Path(__file__).resolve().parents[2] / 'models/manifest.json'


class DownloadModelTests(unittest.TestCase):
    def test_sources_match_manifest(self):
        model = next(m for m in json.loads(MANIFEST.read_text())['models'] if m['id'] == 'blurball-pretrained-v1')
        self.assertEqual(model['weights_url'], WEIGHTS_URL)
        self.assertEqual(model['weights_bytes'], download_model.WEIGHTS_BYTES)
        self.assertEqual(model['weights_sha256'], WEIGHTS_SHA256)
        self.assertEqual(tuple(model.get('weights_mirrors', [])), download_model.WEIGHTS_MIRRORS)

    def test_user_mirrors_first_and_validated(self):
        with mock.patch.dict(os.environ, {download_model.MIRRORS_ENV: 'https://a.example/w, https://a.example/w\nhttp://b.example/w'}):
            urls = download_model.sources()
        self.assertEqual(urls[:2], ['https://a.example/w', 'http://b.example/w'])
        self.assertEqual(urls[-1], WEIGHTS_URL)
        with mock.patch.dict(os.environ, {download_model.MIRRORS_ENV: 'file:///etc/passwd'}):
            with self.assertRaises(ValueError):
                download_model.sources()

    def test_rotates_sources_and_drops_wrong_files(self):
        calls = []

        def fetch(url, target):
            calls.append(url)
            if url == 'bad-hash':
                return '0' * 64
            if url == 'gone':
                raise urllib.error.HTTPError(url, 404, 'nope', {}, io.BytesIO())
            if url == 'flaky' and calls.count('flaky') < 2:
                raise OSError('EOF')
            return WEIGHTS_SHA256

        with mock.patch.object(download_model, 'fetch', fetch):
            errors = download_model.download_any(['bad-hash', 'gone', 'flaky'], None, sleep=lambda _: None)
        self.assertIsNone(errors)
        # Wrong-content and 404 sources are not retried; the flaky one is.
        self.assertEqual(calls, ['bad-hash', 'gone', 'flaky', 'flaky'])

        with mock.patch.object(download_model, 'fetch', side_effect=OSError('EOF')):
            errors = download_model.download_any(['x://h1/w'], None, rounds=3, sleep=lambda _: None)
        self.assertEqual(errors, {'h1': 'EOF'})


if __name__ == '__main__':
    unittest.main()

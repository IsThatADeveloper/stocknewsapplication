"""Offline local HTTP smoke tests for VS Code and Vercel-compatible endpoints."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import launch


class TestLocalServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = launch.make_server(port=0)
        cls.root = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def fetch(self, path):
        try:
            with urlopen(self.root + path, timeout=3) as response:
                return response.status, response.read(), response.headers.get('Content-Type', '')
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get('Content-Type', '')

    def test_pages_and_rewrites(self):
        for path in ('/', '/index.html', '/stock-search.html', '/halts.html', '/splits.html'):
            status, body, content_type = self.fetch(path)
            self.assertEqual(status, 200, path)
            self.assertIn('text/html', content_type)
            self.assertIn(b'StockDash', body)

    def test_health_and_invalid_api(self):
        status, body, _ = self.fetch('/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'ok')
        self.assertEqual(self.fetch('/api/nonexistent')[0], 404)
        self.assertEqual(self.fetch('/api/news?ticker=SPAI/../../')[0], 400)

    def test_no_open_proxy(self):
        status, body, _ = self.fetch('/api/proxy?url=https%3A%2F%2Fevil.example%2F')
        self.assertEqual(status, 403)
        self.assertIn('not an allowed', json.loads(body)['error'])

    def test_news_endpoint_and_alias(self):
        fixture = {
            'ticker': 'SPAI', 'articles': [{'title':'Sample','publishedAt':'2026-11-09T20:00:00Z'}],
            'providers': [{'name':'StockTitan RSS','status':'ok','count':1}]
        }
        with patch.object(launch, 'get_news', return_value=fixture) as mock_news:
            for path in ('/api/news?ticker=SPAI', '/api/stock?ticker=SPAI'):
                status, body, content_type = self.fetch(path)
                self.assertEqual(status, 200)
                self.assertIn('application/json', content_type)
                self.assertEqual(json.loads(body)['articles'][0]['title'], 'Sample')
            self.assertEqual(mock_news.call_count, 2)

    def test_quote_endpoint(self):
        with patch.object(launch, 'get_quote', return_value={'ticker':'SPAI','stats':{}}):
            status, body, _ = self.fetch('/api/quote?ticker=SPAI')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['ticker'], 'SPAI')


if __name__ == '__main__':
    unittest.main()

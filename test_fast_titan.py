"""RSS fallback tests; direct HTML parser tested separately."""
import unittest
from unittest.mock import patch
import stockdash_backend as b

RSS = b'''<?xml version="1.0"?><rss><channel>
<item><title>SPAI Wins Contract | SPAI Stock News</title><link>https://www.stocktitan.net/news/SPAI/contract.html</link><pubDate>Mon, 09 Nov 2026 20:01:00 GMT</pubDate></item>
<item><title>Other ticker | OMH Stock News</title><link>https://www.stocktitan.net/news/OMH/other.html</link><pubDate>Mon, 09 Nov 2026 20:02:00 GMT</pubDate></item>
</channel></rss>'''

class TestRSSFallback(unittest.TestCase):
    def setUp(self): b.CACHE.clear()
    def test_exact_ticker(self):
        with patch.object(b, 'load_url', return_value=RSS):
            news = b.titan_items('SPAI')
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]['title'], 'SPAI Wins Contract')
    def test_ticker_not_present(self):
        with patch.object(b, 'load_url', return_value=RSS):
            self.assertEqual(b.titan_items('AAPL'), [])

if __name__ == '__main__': unittest.main()

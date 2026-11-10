"""Offline tests based on the StockTitan HTML structure provided by the user."""
import unittest
from unittest.mock import patch
import stockdash_backend as b
from stocktitan_html import parse_news_html

HTML = '''<!doctype html><html><body>
<div class="d-lg-flex mb-3">
  <div class="news-feed-content small lh-sm col">
    <div class="news-card-headline companies-feed-border-gradient">
      <div class="news-row-header"><time datetime="2026-10-29T12:02:00.000Z" class="companies-new-row-datetime text-secondary"><span data-role="date">10/29/2026</span><span data-role="time">08:02 AM</span></time></div>
      <div name="title" class="companies-news-title"><h2><a href="/news/SPAI/safe-pro-contract.html">Safe Pro Completes U.S. Air Force Contract</a></h2></div>
    </div>
    <div class="companies-card-summary"><div class="title">Rhea-AI Summary</div><p><b>Safe Pro Group (SPAI)</b> completed all research milestones.</p><p>Company intends to pursue additional contracts.</p></div>
  </div>
  <div class="companies-rhea-scores news-row-left-group">
    <div class="impact-bar" role="img" aria-label="Impact: Moderate"><span class="dot full"></span></div>
    <div class="sentiment-bar" role="img" aria-label="Sentiment: Positive"></div>
    <span class="badge badge-neutral">0.00%</span>
    <div name="tags" class="companies-list-tags notranslate"><span class="badge tag"><a href="/news/ai.html">AI</a></span></div>
  </div>
</div>
<div class="d-lg-flex mb-3"><div class="news-feed-content">
 <time datetime="2026-10-08T12:05:00.000Z"></time>
 <div class="companies-news-title"><h2><a href="https://www.stocktitan.net/news/SPAI/older.html">Older SPAI news</a></h2></div>
 <div class="companies-card-summary"><p>Second article.</p></div>
</div></div>
<div class="d-lg-flex mb-3"><div class="news-feed-content">
 <time datetime="2026-11-09T12:05:00.000Z"></time>
 <div class="companies-news-title"><a href="/news/OMH/not-spai.html">Wrong ticker</a></div>
</div></div>
</body></html>'''

RSS = b'''<rss><channel><item><title>SPAI Newer Release | SPAI Stock News</title><link>https://www.stocktitan.net/news/SPAI/newer.html</link><pubDate>Mon, 09 Nov 2026 20:00:00 GMT</pubDate></item></channel></rss>'''


class TestDirectTitan(unittest.TestCase):
    def setUp(self):
        b.CACHE.clear()

    def test_user_supplied_html_selectors(self):
        news = parse_news_html(HTML, 'SPAI')
        self.assertEqual(len(news), 2)
        first = news[0]
        self.assertEqual(first['title'], 'Safe Pro Completes U.S. Air Force Contract')
        self.assertEqual(first['publishedAt'], '2026-10-29T12:02:00Z')
        self.assertEqual(first['url'], 'https://www.stocktitan.net/news/SPAI/safe-pro-contract.html')
        self.assertEqual(first['summary'], 'Safe Pro Group (SPAI) completed all research milestones. Company intends to pursue additional contracts.')
        self.assertEqual(first['impact'], 'Impact: Moderate')
        self.assertEqual(first['sentiment'], 'Sentiment: Positive')
        self.assertEqual(first['eod'], '0.00%')
        self.assertEqual(first['tags'], ['AI'])

    def test_direct_mode_does_not_call_rss(self):
        calls = []
        def stub(url, **kwargs):
            calls.append(url)
            if url == 'https://www.stocktitan.net/news/SPAI/':
                return HTML.encode('utf8')
            raise AssertionError('Unexpected URL: ' + url)
        with patch.object(b, 'load_url', side_effect=stub):
            result = b.get_news('spai')
        self.assertEqual(calls, ['https://www.stocktitan.net/news/SPAI/'])
        self.assertEqual(result['primarySource'], 'StockTitan company page')
        self.assertEqual(result['articles'][0]['impact'], 'Impact: Moderate')
        self.assertEqual(result['providers'][0]['status'], 'ok')

    def test_fallback_if_page_unavailable(self):
        def stub(url, **kwargs):
            if url.endswith('/news/SPAI/'):
                raise PermissionError('403')
            if url.endswith('/rss'):
                return RSS
            raise AssertionError('Unexpected URL')
        with patch.object(b, 'load_url', side_effect=stub):
            result = b.get_news('SPAI')
        self.assertEqual(result['primarySource'], 'StockTitan RSS fallback')
        self.assertEqual(result['providers'][0]['status'], 'error')
        self.assertEqual(result['providers'][1]['status'], 'ok')
        self.assertEqual(result['articles'][0]['source'], 'StockTitan RSS')
        self.assertTrue(result['warnings'])

    def test_no_cards_falls_back_instead_of_false_zero(self):
        def stub(url, **kwargs):
            return b'<html><title>Just a moment</title></html>' if '/news/SPAI/' in url else RSS
        with patch.object(b, 'load_url', side_effect=stub):
            result = b.get_news('SPAI')
        self.assertEqual(result['primarySource'], 'StockTitan RSS fallback')
        self.assertEqual(len(result['articles']), 1)

    def test_bad_ticker_rejected(self):
        for symbol in ('', '../SPAI', 'A;B', 'https://example.com/'):
            with self.assertRaises(ValueError):
                b.get_news(symbol)

    def test_offsite_article_rejected(self):
        injected = HTML.replace('https://www.stocktitan.net/news/SPAI/older.html', 'https://example.com/news/SPAI/older.html')
        self.assertEqual(len(parse_news_html(injected, 'SPAI')), 1)

if __name__ == '__main__':
    unittest.main()

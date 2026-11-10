#!/usr/bin/env python3
"""StockDash backend for local Python and Vercel. Direct ticker-page attempt, RSS fallback."""
from __future__ import annotations

import calendar
import email.utils
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from stocktitan_html import parse_news_html

ROOT = Path(__file__).resolve().parent
USER_AGENT = 'StockDash Personal News Reader/1.1'
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
FEED_CACHE_SECONDS = 15
ALLOWED_PROXY_URLS = {
    'https://www.nyse.com/api/trade-halts/current/download': 'text/csv; charset=utf-8',
    'https://stockanalysis.com/actions/splits/': 'text/html; charset=utf-8',
}
CACHE = {}
CACHE_LOCK = threading.Lock()
TICKER_RE = re.compile(r'^[A-Z][A-Z0-9.\-]{0,9}$')
HTML_TAGS = re.compile(r'<[^>]+>')


def read_dotenv():
    """Optional FINNHUB_API_KEY in .env; no dependencies or key in HTML."""
    env_file = ROOT / '.env'
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        name, value = line.split('=', 1)
        if name.strip() == 'FINNHUB_API_KEY':
            os.environ.setdefault('FINNHUB_API_KEY', value.strip().strip('\"\''))


def load_url(url, *, headers=None, max_bytes=MAX_RESPONSE_BYTES, timeout=9):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': USER_AGENT,
            'Accept': 'application/rss+xml, application/xml, text/xml, application/json, text/html, */*',
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if int(response.headers.get('Content-Length') or 0) > max_bytes:
            raise ValueError('Upstream response too large')
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError('Upstream response too large')
        return raw


def cached(key, loader, ttl=FEED_CACHE_SECONDS):
    now = time.monotonic()
    with CACHE_LOCK:
        entry = CACHE.get(key)
        if entry and entry[0] > now:
            return entry[1]
    value = loader()
    with CACHE_LOCK:
        CACHE[key] = (time.monotonic() + ttl, value)
    return value


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(HTML_TAGS.sub(' ', value or ''))).strip()


def parsed_iso(raw):
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def first_text(item, tags):
    for tag in tags:
        el = item.find(tag)
        if el is not None and el.text:
            return el.text.strip()
    return ''


def rss_items(raw):
    root = ET.fromstring(raw)
    items = []
    for item in root.findall('.//item'):
        title = clean(first_text(item, ['title']))
        link = first_text(item, ['link'])
        if not title or not link:
            continue
        category = clean(first_text(item, ['category']))
        items.append({
            'title': title,
            'url': link,
            'summary': clean(first_text(item, ['description']))[:500],
            'publishedAt': parsed_iso(first_text(item, ['pubDate', '{http://purl.org/dc/elements/1.1/}date'])),
            'tags': [category] if category else [],
        })
    # Atom as a fallback if feed provider changes format.
    if not items:
        atom = '{http://www.w3.org/2005/Atom}'
        for entry in root.findall(f'.//{atom}entry'):
            link = entry.find(f'{atom}link')
            url = (link.attrib.get('href') or '') if link is not None else ''
            title = clean(first_text(entry, [f'{atom}title']))
            if title and url:
                items.append({
                    'title': title, 'url': url,
                    'summary': clean(first_text(entry, [f'{atom}summary']))[:500],
                    'publishedAt': parsed_iso(first_text(entry, [f'{atom}published', f'{atom}updated'])),
                    'tags': [],
                })
    return items


def safe_web_url(value):
    try:
        u = urllib.parse.urlsplit(value)
    except (TypeError, ValueError):
        return False
    return u.scheme in ('http', 'https') and bool(u.netloc)


def titan_page_items(ticker):
    """Request the public ticker page once; no login, CAPTCHA or block evasion.

    If the upstream denies the request or returns non-article content, the
    caller falls back to the explicitly permitted RSS integration.
    """
    url = f'https://www.stocktitan.net/news/{urllib.parse.quote(ticker, safe="")}/'

    def fetch():
        raw = load_url(url, timeout=7)
        return parse_news_html(raw.decode('utf-8-sig', errors='replace'), ticker)

    return cached('stocktitan:page:' + ticker, fetch, ttl=FEED_CACHE_SECONDS)


def titan_items(ticker):
    """Match a ticker exactly using the canonical StockTitan article URL.

    If the RSS feed changes its link structure, accept the explicit
    "| SYMBOL Stock News" suffix only for links on StockTitan's own domain.
    """
    all_items = cached('stocktitan:rss', lambda: rss_items(load_url('https://www.stocktitan.net/rss')))
    items = []
    for entry in all_items:
        if not safe_web_url(entry['url']):
            continue
        url = urllib.parse.urlsplit(entry['url'])
        if (url.hostname or '').lower() not in ('stocktitan.net', 'www.stocktitan.net'):
            continue
        slug = re.search(r'/news/([^/]+)/', url.path, re.I)
        linked_ticker = urllib.parse.unquote(slug.group(1)).upper() if slug else None
        titled = re.search(r'\|\s*([A-Z0-9.\-]+)\s+Stock News\s*$', entry['title'], re.I)
        titled_ticker = titled.group(1).upper() if titled else None
        # Never allow an explicit mismatch in the URL to be overridden by a title.
        if linked_ticker and linked_ticker != ticker:
            continue
        if (linked_ticker or titled_ticker) != ticker:
            continue
        title = entry['title'][:titled.start()].strip() if titled else entry['title']
        items.append({**entry, 'title': title, 'source': 'StockTitan RSS'})
    return items


def google_items(ticker):
    query = f'"{ticker}" stock'
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
        'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en',
    })
    return [
        {**entry, 'source': 'Google News'}
        for entry in cached('google:' + ticker, lambda: rss_items(load_url(url)), ttl=90)[:40]
        if safe_web_url(entry['url'])
    ]


def finnhub_items(ticker, key):
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=90)
    url = 'https://finnhub.io/api/v1/company-news?' + urllib.parse.urlencode({
        'symbol': ticker, 'from': start.isoformat(), 'to': today.isoformat(),
    })

    def fetch():
        data = json.loads(load_url(url, headers={'X-Finnhub-Token': key}))
        if not isinstance(data, list):
            raise ValueError('Unexpected Finnhub response')
        found = []
        for item in data[:150]:
            link = item.get('url', '')
            title = item.get('headline', '')
            if not title or not safe_web_url(link):
                continue
            stamp = item.get('datetime')
            try:
                published = datetime.fromtimestamp(int(stamp), tz=timezone.utc).isoformat().replace('+00:00', 'Z')
            except (ValueError, TypeError, OverflowError, OSError):
                published = None
            found.append({
                'title': str(title).strip(), 'url': link,
                'summary': str(item.get('summary') or '')[:500],
                'publishedAt': published,
                'source': 'Finnhub', 'tags': [],
            })
        return found

    return cached('finnhub:' + ticker, fetch, ttl=60)


def yahoo_quote(ticker):
    """Optional public price context; never assume live quotes or float values."""
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(ticker) + '?' + urllib.parse.urlencode({
        'range': '3mo', 'interval': '1d',
    })

    def fetch():
        result = json.loads(load_url(url))['chart']['result'][0]
        meta = result.get('meta') or {}
        stats = {}
        if isinstance(meta.get('regularMarketPrice'), (int, float)):
            stats['Price (last reported)'] = f"{meta.get('currency', 'USD')} {meta['regularMarketPrice']:,.2f}"
        previous = meta.get('previousClose', meta.get('chartPreviousClose'))
        if isinstance(previous, (int, float)):
            stats['Previous Close'] = f"{meta.get('currency', 'USD')} {previous:,.2f}"
        volumes = (result.get('indicators') or {}).get('quote') or []
        if volumes:
            vv = [float(v) for v in (volumes[0].get('volume') or []) if isinstance(v, (int, float)) and v >= 0]
            if vv:
                stats['Avg Volume (3 months approx.)'] = f"{sum(vv) / len(vv):,.0f} shares/day"
        market_time = meta.get('regularMarketTime')
        asof = None
        if isinstance(market_time, int):
            asof = datetime.fromtimestamp(market_time, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
        return {'stats': stats, 'quoteAsOf': asof, 'quoteSource': 'Yahoo Finance (potentially delayed)'}

    return cached('quote:' + ticker, fetch, ttl=60)


def article_key(title):
    return re.sub(r'[^a-z0-9 ]+', '', title.lower()).strip()[:120]


def validate_ticker(ticker_input):
    ticker = (ticker_input or '').strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError('Enter a valid ticker, such as SPAI, OMH, AAPL, or BRK.B')
    return ticker


def get_quote(ticker_input):
    """Price context separate from the news request to avoid delaying news."""
    ticker = validate_ticker(ticker_input)
    return {'ticker': ticker, **yahoo_quote(ticker)}


def get_news(ticker_input, mode='fast'):
    """Try StockTitan's ticker page first, then authorized RSS on failure.

    In "more" mode, optionally merge other news providers. A failed direct
    request is never represented as "zero company news".
    """
    ticker = validate_ticker(ticker_input)
    if mode not in ('fast', 'more'):
        raise ValueError('mode must be fast or more')
    news, statuses, warnings = [], [], []
    primary_source = 'StockTitan company page'
    try:
        news = titan_page_items(ticker)
        statuses.append({'name': 'StockTitan company page', 'status': 'ok', 'count': len(news)})
    except Exception as exc:
        primary_source = 'StockTitan RSS fallback'
        statuses.append({'name': 'StockTitan company page', 'status': 'error', 'count': 0})
        warnings.append(f'StockTitan ticker page unavailable ({type(exc).__name__}). Using RSS fallback if possible.')
        try:
            news = titan_items(ticker)
            statuses.append({'name': 'StockTitan RSS', 'status': 'ok' if news else 'empty', 'count': len(news)})
        except Exception as feed_exc:
            statuses.append({'name': 'StockTitan RSS', 'status': 'error', 'count': 0})
            warnings.append(f'StockTitan RSS unavailable ({type(feed_exc).__name__}).')
            if mode == 'fast':
                raise RuntimeError('StockTitan page and RSS both unavailable. Open the ticker link directly.') from feed_exc

    if mode == 'more':
        providers = [('Google News', lambda: google_items(ticker))]
        key = os.environ.get('FINNHUB_API_KEY', '').strip()
        if key:
            providers.append(('Finnhub', lambda: finnhub_items(ticker, key)))
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = [(name, pool.submit(loader)) for name, loader in providers]
            for name, future in futures:
                try:
                    stories = future.result()
                    statuses.append({'name': name, 'status': 'ok' if stories else 'empty', 'count': len(stories)})
                    news.extend(stories)
                except Exception as exc:
                    statuses.append({'name': name, 'status': 'error', 'count': 0})
                    warnings.append(f'{name} unavailable ({type(exc).__name__}).')

    news.sort(key=lambda item: item.get('publishedAt') or '', reverse=True)
    seen, items = set(), []
    for story in news:
        # Article title lets us suppress duplicated direct/RSS or provider links.
        key = article_key(story['title'])
        if key and key not in seen:
            seen.add(key)
            items.append(story)
            if len(items) >= 60:
                break

    return {
        'ticker': ticker,
        'mode': mode,
        'primarySource': primary_source,
        'fetchedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'stockTitanUrl': f'https://www.stocktitan.net/news/{ticker}/',
        'articles': items,
        'providers': statuses,
        'warnings': warnings,
        'notes': [
            'Direct access can be denied or break if StockTitan changes its HTML. RSS is used as fallback.',
            'Site publication times and delivery are not guaranteed to be real-time.',
            'StockTitan terms restrict automated extraction even for personal use; obtain permission before automated polling.',
        ],
    }

"""Parse the public-facing StockTitan *ticker news page* HTML.

No Selenium, browser automation, logins, CAPTCHAs, or anti-bot workarounds.
This parser only handles response HTML supplied to it. Site access and rights
are separate concerns; StockTitan may restrict automated access even for
personal projects.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from datetime import datetime, timezone

BASE = 'https://www.stocktitan.net'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr'}


class Element:
    __slots__ = ('tag', 'attrs', 'children', 'parent')

    def __init__(self, tag='', attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.parent = parent

    def attr(self, key):
        return self.attrs.get(key) or ''

    def has_class(self, name):
        return name in self.attr('class').split()

    def walk(self):
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.walk()

    def find(self, predicate):
        return next((e for e in self.walk() if predicate(e)), None)

    def find_class(self, classname):
        return self.find(lambda e: e.has_class(classname))

    def all(self, predicate):
        return [e for e in self.walk() if predicate(e)]

    def text(self):
        def visit(el):
            for child in el.children:
                if isinstance(child, str):
                    yield child
                elif child.tag not in {'script','style','template'}:
                    yield from visit(child)
        return re.sub(r'\s+', ' ', ''.join(visit(self))).strip()


class HTMLTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element('document')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = Element(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def parse_news_html(markup: str, ticker: str):
    """Return newest-first article objects for *exact* ticker, no off-site links."""
    p = HTMLTree()
    p.feed(markup)
    p.close()
    cards = p.root.all(lambda e: e.has_class('news-feed-content'))
    if not cards:
        raise ValueError('StockTitan returned no article cards; the site may have blocked the request or changed its layout')

    found = []
    seen = set()
    for card in cards:
        heading = card.find_class('companies-news-title')
        anchor = heading and heading.find(lambda e: e.tag == 'a' and bool(e.attr('href')))
        stamp_el = card.find(lambda e: e.tag == 'time' and bool(e.attr('datetime')))
        if not anchor or not stamp_el:
            continue

        target = urljoin(BASE, anchor.attr('href'))
        parts = urlsplit(target)
        # Only exact public company news article paths on StockTitan.
        if (parts.scheme != 'https'
            or (parts.hostname or '').lower() not in ('stocktitan.net','www.stocktitan.net')
            or not parts.path.upper().startswith(f'/NEWS/{ticker}/')
            or target in seen):
            continue
        try:
            ts = datetime.fromisoformat(stamp_el.attr('datetime').strip().replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            published_at = ts.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        except (ValueError, TypeError):
            continue

        summary_node = card.find_class('companies-card-summary')
        summary = ''
        if summary_node:
            paragraphs = summary_node.all(lambda e: e.tag == 'p')
            summary = ' '.join(p.text() for p in paragraphs).strip() if paragraphs else summary_node.text()

        # The Rhea-AI panel sits beside .news-feed-content in a .d-lg-flex group.
        container = card.parent
        score = None
        for _ in range(5):
            if container is None:
                break
            if container.has_class('d-lg-flex'):
                score = container.find_class('companies-rhea-scores')
                break
            container = container.parent

        impact = sentiment = eod = ''
        tags = []
        if score:
            imp = score.find_class('impact-bar')
            sent = score.find_class('sentiment-bar')
            end_of_day = score.find_class('badge-neutral')
            impact = imp.attr('aria-label') if imp else ''
            sentiment = sent.attr('aria-label') if sent else ''
            eod = end_of_day.text() if end_of_day else ''
            tags_container = score.find_class('companies-list-tags')
            if tags_container:
                tags = [e.text() for e in tags_container.all(lambda e: e.has_class('tag'))]
                tags = [x for x in tags if x][:10]

        title = anchor.text()
        if not title:
            continue
        seen.add(target)
        found.append({
            'title': title,
            'url': target,
            'publishedAt': published_at,
            'summary': summary[:2400],
            'source': 'StockTitan company page',
            'tags': tags,
            'impact': impact,
            'sentiment': sentiment,
            'eod': eod,
        })

    if not found:
        raise ValueError(f'No matching {ticker} articles could be parsed from StockTitan HTML')
    found.sort(key=lambda item: item['publishedAt'], reverse=True)
    return found[:60]

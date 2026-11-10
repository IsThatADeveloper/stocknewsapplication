#!/usr/bin/env python3
"""Run StockDash locally in VS Code/Visual Studio or a terminal.

This is an HTTP server for development only. Vercel uses the files in api/.
No third-party Python packages needed.

Usage:
    python launch.py
    python launch.py --port 8080
    python launch.py --no-browser
"""
from __future__ import annotations

import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import parse_qs, urlsplit
import webbrowser

from stockdash_backend import (
    ALLOWED_PROXY_URLS, cached, get_news, get_quote, load_url, read_dotenv,
)

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'


class StockDashHandler(SimpleHTTPRequestHandler):
    """Serve public/ files and match the same API routes deployed to Vercel."""

    def json_response(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.binary_response(status, body, 'application/json; charset=utf-8')

    def binary_response(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        route = url.path.rstrip('/') or '/'
        qs = parse_qs(url.query)

        if route == '/api/health':
            return self.json_response(200, {'status': 'ok'})
        if route in ('/api/news', '/api/stock'):
            ticker = qs.get('ticker', [''])[0]
            mode = qs.get('mode', ['fast'])[0]
            try:
                result = get_news(ticker, mode=mode)
            except ValueError as exc:
                return self.json_response(400, {'error': str(exc)})
            except Exception as exc:
                return self.json_response(502, {'error': f'News feed unavailable: {exc}'})
            return self.json_response(200, result)
        if route == '/api/quote':
            ticker = qs.get('ticker', [''])[0]
            try:
                result = get_quote(ticker)
            except ValueError as exc:
                return self.json_response(400, {'error': str(exc)})
            except Exception:
                return self.json_response(502, {'error': 'Quote provider unavailable'})
            return self.json_response(200, result)
        if route == '/api/proxy':
            target = qs.get('url', [''])[0]
            content_type = ALLOWED_PROXY_URLS.get(target)
            if not content_type:
                return self.json_response(403, {'error': 'This URL is not an allowed market-data source'})
            try:
                data = cached('proxy:' + target, lambda: load_url(target), ttl=30)
            except Exception as exc:
                return self.json_response(502, {'error': f'Upstream market-data source failed: {exc}'})
            return self.binary_response(200, data, content_type)
        if route == '/api' or route.startswith('/api/'):
            return self.json_response(404, {'error': 'API route not found'})

        # Vercel rewrites / and /stock-search.html to index.html.
        if route in ('/', '/stock-search.html'):
            self.path = '/index.html'
        return super().do_GET()


def make_server(port=8000, host='127.0.0.1'):
    """Start an HTTP server, not a file:// page (which breaks /api routes)."""
    if not PUBLIC.is_dir():
        raise FileNotFoundError(f'Missing {PUBLIC} — run from the complete project folder')
    handler = partial(StockDashHandler, directory=str(PUBLIC))
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='Run StockDash locally')
    parser.add_argument('--port', type=int, default=int(os.environ.get('STOCKDASH_PORT', '8000')))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    read_dotenv()
    try:
        server = make_server(port=args.port)
    except OSError as exc:
        parser.exit(1, f'Could not start on port {args.port}: {exc}\nTry python launch.py --port 8080\n')

    url = f'http://127.0.0.1:{server.server_port}/'
    print('\nStockDash is running locally!', flush=True)
    print(f'Stock Search:   {url}', flush=True)
    print(f'Trading Halts:  {url}halts.html', flush=True)
    print(f'Stock Splits:   {url}splits.html', flush=True)
    print(f'API status:     {url}api/health', flush=True)
    print('Press Ctrl+C to stop.\n', flush=True)
    if not args.no_browser:
        timer = Timer(0.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print('\nStopping StockDash...', flush=True)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

"""GET /api/proxy?url=... — restricted upstream market-data fetch."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
from urllib.parse import urlsplit, parse_qs
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stockdash_backend import ALLOWED_PROXY_URLS, load_url, cached


class handler(BaseHTTPRequestHandler):
    def respond(self, status, data, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        self.respond(status, json.dumps({'error': message}).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        url = parse_qs(urlsplit(self.path).query).get('url', [''])[0]
        content_type = ALLOWED_PROXY_URLS.get(url)
        if not content_type:
            return self.error(403, 'This URL is not an allowed market-data source')
        try:
            data = cached('proxy:' + url, lambda: load_url(url), ttl=30)
            return self.respond(200, data, content_type)
        except Exception as exc:
            return self.error(502, f'Upstream market-data source failed: {exc}')

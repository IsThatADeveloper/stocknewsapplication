"""GET /api/news?ticker=SPAI — stock news endpoint for Vercel."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import sys
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stockdash_backend import get_news


class handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        params = parse_qs(urlsplit(self.path).query)
        ticker = params.get('ticker', [''])[0]
        mode = params.get('mode', ['fast'])[0]
        try:
            self.reply(200, get_news(ticker, mode=mode))
        except ValueError as exc:
            self.reply(400, {'error': str(exc)})
        except Exception as exc:
            self.reply(502, {'error': str(exc)})

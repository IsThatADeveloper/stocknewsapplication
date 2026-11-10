"""GET /api/quote?ticker=SPAI — optional delayed price context."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import sys
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stockdash_backend import get_quote


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ticker = parse_qs(urlsplit(self.path).query).get('ticker', [''])[0]
        try:
            payload = get_quote(ticker)
            status = 200
        except ValueError as exc:
            payload, status = {'error': str(exc)}, 400
        except Exception:
            payload, status = {'error': 'Quote provider unavailable'}, 502
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

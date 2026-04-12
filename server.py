import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

from auth import get_app, get_token
from config import TENANT_ID, PORT
from api.activity  import handle_activity
from api.capacity  import handle_capacity
from api.timepoint import handle_timepoint
from api.refreshes import handle_refreshes

_here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_here, "static", "index.html"), encoding="utf-8") as _f:
    _HTML = _f.read().encode()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {fmt % args}")

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(_HTML))
            self.end_headers()
            self.wfile.write(_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length)) if length else {}
        try:
            if   self.path == "/api/ping":        self.send_json(200, {"status": "ok"})
            elif self.path == "/api/auth_status": self._auth_status()
            elif self.path == "/api/activity":    self.send_json(200, handle_activity(payload))
            elif self.path == "/api/capacity":    self.send_json(200, handle_capacity(payload))
            elif self.path == "/api/timepoint":   self.send_json(200, handle_timepoint(payload))
            elif self.path == "/api/refreshes":   self.send_json(200, handle_refreshes(payload))
            else:                                 self.send_json(404, {"error": "Endpoint desconhecido"})
        except Exception as e:
            print(f"  ERRO: {e}")
            self.send_json(500, {"error": str(e)})

    def _auth_status(self):
        accounts = get_app().get_accounts()
        if accounts:
            self.send_json(200, {"authenticated": True, "account": accounts[0].get("username", "")})
        else:
            self.send_json(200, {"authenticated": False, "account": ""})


def main():
    print("\n" + "═" * 60)
    print("  FABRIC ACTIVITY MONITOR")
    print("═" * 60)
    print(f"\n  Tenant: {TENANT_ID}")
    print(f"\n  A autenticar...\n")

    try:
        get_token()
    except Exception as e:
        print(f"  AVISO: {e}")

    print(f"\n  ✓ Proxy activo — abre o browser em: http://localhost:{PORT}\n")

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Proxy parado.")

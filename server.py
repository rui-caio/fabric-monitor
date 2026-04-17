import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from auth import get_app, get_token
from config import TENANT_ID, PORT, ORG_NAME, FM_DISPLAY_JS
from api.activity  import handle_activity
from api.capacity  import handle_capacity
from api.timepoint import handle_timepoint
from api.refreshes import handle_refreshes
from api.inventory import handle_inventory

_auth_thread = None
_auth_thread_lock = threading.Lock()



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
            _here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(_here, "static", "index.html"), encoding="utf-8") as _f:
                html = (
                    _f.read()
                    .replace("{{ORG_NAME}}", ORG_NAME)
                    .replace("__FM_DISPLAY__", FM_DISPLAY_JS)
                    .encode()
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
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
            elif self.path == "/api/inventory":   self.send_json(200, handle_inventory(payload))
            elif self.path == "/api/domain_status":
                from api.domains import get_domain_status
                self.send_json(200, get_domain_status())
            else:                                 self.send_json(404, {"error": "Unknown endpoint"})

        except Exception as e:
            print(f"  ERROR: {e}")
            self.send_json(500, {"error": str(e)})

    def _auth_status(self):
        accounts = get_app().get_accounts()
        authenticating = _auth_thread is not None and _auth_thread.is_alive()
        if accounts:
            self.send_json(200, {
                "authenticated": True,
                "account": accounts[0].get("username", ""),
                "authenticating": authenticating,
            })
        else:
            if not authenticating:
                _ensure_auth_thread()
                authenticating = True
            self.send_json(200, {
                "authenticated": False,
                "account": "",
                "authenticating": authenticating,
            })


def _authenticate_background():
    try:
        get_token()
    except Exception as e:
        print(f"  WARNING: {e}")


def _ensure_auth_thread():
    global _auth_thread
    with _auth_thread_lock:
        if _auth_thread is None or not _auth_thread.is_alive():
            _auth_thread = threading.Thread(target=_authenticate_background, daemon=True)
            _auth_thread.start()


def main():
    print("\n" + "═" * 60)
    print("  FABRIC ACTIVITY MONITOR")
    print("═" * 60)
    print(f"\n  Tenant: {TENANT_ID}")
    print("\n  Sign in first (device code appears below if required).\n")

    try:
        get_token()
        from api.domains import load_domains_map
        load_domains_map()
    except Exception as e:
        print(f"\n  ERROR: Sign-in failed: {e}")
        print("  Fix the issue and restart.\n")
        return


    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        local_ip = "127.0.0.1"

    print(f"  ✓ Proxy ready — open the report in your browser:")
    print(f"    Local:   http://localhost:{PORT}")
    print(f"    Network: http://{local_ip}:{PORT}\n")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Proxy stopped.")

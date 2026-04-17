import json
import threading
import urllib.request
import urllib.error
import sys

try:
    import msal
except ImportError:
    print("\n  ERROR: 'msal' library not found.")
    print("  Install with: pip install msal\n")
    sys.exit(1)

from config import TENANT_ID, PUBLIC_CLIENT_ID, SCOPES

# Microsoft Fabric REST (List Items). Inventory uses silent acquisition only — no second device login.
FABRIC_SCOPES = ["https://api.fabric.microsoft.com/Workspace.Read.All"]

import os
import atexit

CACHE_FILE = ".token_cache.bin"
_token_cache = msal.SerializableTokenCache()

if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r") as f:
            _token_cache.deserialize(f.read())
    except Exception as e:
        print(f"  Warning: failed to load token cache: {e}")

def _save_cache():
    if _token_cache.has_state_changed:
        with open(CACHE_FILE, "w") as f:
            f.write(_token_cache.serialize())

atexit.register(_save_cache)

_auth_lock   = threading.Lock()
_auth_info   = {"account": ""}

def get_app():
    return msal.PublicClientApplication(
        PUBLIC_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=_token_cache,
    )


def get_token(scopes=None):
    if scopes is None:
        scopes = SCOPES
    with _auth_lock:
        app      = get_app()
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]

        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise Exception("Device Code flow failed: " + json.dumps(flow))

        print("\n" + "-" * 60, flush=True)
        print("  AUTHENTICATION REQUIRED", flush=True)
        print("-" * 60, flush=True)
        print(f"\n  1. Open: https://microsoft.com/devicelogin", flush=True)
        print(f"  2. Code: {flow['user_code']}", flush=True)
        print(f"\n  Waiting...\n", flush=True)

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise Exception("Failed: " + result.get("error_description", str(result)))

        accounts = get_app().get_accounts()
        if accounts:
            _auth_info["account"] = accounts[0].get("username", "")
        print(f"  ✓ Authenticated as {_auth_info['account']}\n", flush=True)
        return result["access_token"]



def try_fabric_token_silent():
    """
    Returns an access token for api.fabric.microsoft.com if the user has already
    consented to Workspace.Read.All (cached). Otherwise returns None — never blocks
    on device code (inventory falls back to Power BI REST only).
    """
    with _auth_lock:
        app = get_app()
        accounts = app.get_accounts()
        if not accounts:
            return None
        result = app.acquire_token_silent(FABRIC_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
        return None


def call_api(url, token):
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}

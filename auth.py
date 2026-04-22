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

from config import (
    AUTH_TYPE,
    CLIENT_ID,
    CLIENT_SECRET,
    PUBLIC_CLIENT_ID,
    SCOPES,
    TENANT_ID,
    FABRIC_DELEGATE_SCOPES,
)

# CCA: one resource = one .default; application permissions are in the app registration
PBI_CCA_SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]
FABRIC_CCA_SCOPES = ["https://api.fabric.microsoft.com/.default"]

import os
import atexit

CACHE_FILE = ".token_cache.bin"
_token_cache = msal.SerializableTokenCache()

if AUTH_TYPE == "public" and os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r") as f:
            _token_cache.deserialize(f.read())
    except Exception as e:
        print(f"  Warning: failed to load token cache: {e}")


def _save_cache():
    if AUTH_TYPE != "public":
        return
    if _token_cache.has_state_changed:
        with open(CACHE_FILE, "w") as f:
            f.write(_token_cache.serialize())


atexit.register(_save_cache)

_auth_lock = threading.Lock()
_auth_info = {"account": ""}
_confidential_app = None


def get_app():
    """MSAL public client; only for AUTH_TYPE=public. Returns None for client credentials."""
    if AUTH_TYPE == "client_secret":
        return None
    return msal.PublicClientApplication(
        PUBLIC_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=_token_cache,
    )


def get_confidential_app():
    global _confidential_app
    if _confidential_app is None:
        _confidential_app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        )
    return _confidential_app


def _resource_cca_scopes_for_request(scopes):
    """
    For client credentials, use each API's .default. Map Fabric vs Power BI from the
    first requested scope.
    """
    s0 = (scopes[0] if isinstance(scopes, (list, tuple)) and scopes else str(scopes or "")).lower()
    if "fabric.microsoft.com" in s0:
        return FABRIC_CCA_SCOPES
    return PBI_CCA_SCOPES


def get_token(scopes=None):
    if scopes is None:
        scopes = SCOPES
    with _auth_lock:
        if AUTH_TYPE == "client_secret":
            app = get_confidential_app()
            cca_scopes = _resource_cca_scopes_for_request(scopes)
            # acquire_token_for_client looks up the cache first (MSAL 1.23+)
            result = app.acquire_token_for_client(cca_scopes)
            if result and "access_token" in result:
                return result["access_token"]
            err = result.get("error_description", result) if result else "unknown"
            raise Exception("Client credentials failed: " + str(err))

        app = get_app()
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
    For public: return a Fabric token only if the user has already consented (cached) — no device code.
    For client credentials: acquire a Fabric .default token (fails with None if the app has no app permission).
    """
    with _auth_lock:
        if AUTH_TYPE == "client_secret":
            result = get_confidential_app().acquire_token_for_client(FABRIC_CCA_SCOPES)
            if result and "access_token" in result:
                return result["access_token"]
            return None

        app = get_app()
        accounts = app.get_accounts()
        if not accounts:
            return None
        result = app.acquire_token_silent(FABRIC_DELEGATE_SCOPES, account=accounts[0])
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

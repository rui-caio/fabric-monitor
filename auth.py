import json
import threading
import urllib.request
import urllib.error
import sys

try:
    import msal
except ImportError:
    print("\n  ERRO: biblioteca 'msal' não encontrada.")
    print("  Instala com: pip install msal\n")
    sys.exit(1)

from config import TENANT_ID, PUBLIC_CLIENT_ID, SCOPES

_token_cache = msal.SerializableTokenCache()
_auth_lock   = threading.Lock()
_auth_info   = {"account": ""}


def get_app():
    return msal.PublicClientApplication(
        PUBLIC_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=_token_cache,
    )


def get_token():
    with _auth_lock:
        app      = get_app()
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]

        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise Exception("Falha Device Code: " + json.dumps(flow))

        print("\n" + "─" * 60)
        print("  AUTENTICAÇÃO NECESSÁRIA")
        print("─" * 60)
        print(f"\n  1. Abre: https://microsoft.com/devicelogin")
        print(f"  2. Código: {flow['user_code']}")
        print(f"\n  À espera...\n")

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise Exception("Falhou: " + result.get("error_description", str(result)))

        accounts = get_app().get_accounts()
        if accounts:
            _auth_info["account"] = accounts[0].get("username", "")
        print(f"  ✓ Autenticado como {_auth_info['account']}\n")
        return result["access_token"]


def call_api(url, token):
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}

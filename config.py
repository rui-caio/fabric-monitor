import json
import os
import sys

def _load_env(path=None):
    """Loads variables from a .env file into os.environ (no external dependencies)."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)
    except FileNotFoundError:
        pass


_load_env()

TENANT_ID   = os.environ.get("TENANT_ID", "")
CAPACITY_ID = os.environ.get("CAPACITY_ID", "")
METRICS_WS  = os.environ.get("METRICS_WS", "")
METRICS_DS  = os.environ.get("METRICS_DS", "")
PORT        = int(os.environ.get("PORT", "8765"))
ORG_NAME    = os.environ.get("ORG_NAME", "")

# Display time for UI (optional). Prefer IANA zone (DST-aware); else fixed offset from UTC in hours.
DISPLAY_TIMEZONE = os.environ.get("DISPLAY_TIMEZONE", "").strip() or None
_off = os.environ.get("DISPLAY_UTC_OFFSET_HOURS", "").strip()
try:
    DISPLAY_UTC_OFFSET_HOURS = float(_off) if _off else None
except ValueError:
    DISPLAY_UTC_OFFSET_HOURS = None

FM_DISPLAY_JS = json.dumps(
    {"timeZone": DISPLAY_TIMEZONE, "utcOffsetHours": DISPLAY_UTC_OFFSET_HOURS},
    ensure_ascii=False,
)

_missing = [k for k, v in {
    "TENANT_ID": TENANT_ID, "CAPACITY_ID": CAPACITY_ID,
    "METRICS_WS": METRICS_WS, "METRICS_DS": METRICS_DS,
}.items() if not v]
if _missing:
    print(f"\n  ERROR: unconfigured variables: {', '.join(_missing)}")
    print("  Copy .env.example to .env and fill in the values.\n")
    sys.exit(1)

# Authentication: "public" (device code, interactive) or "client_secret" (service principal).
# Aliases: client_credentials → client_secret
_raw_auth = (os.environ.get("AUTH_TYPE") or "public").strip().lower()
if _raw_auth in ("client_secret", "client_credentials", "sp"):
    AUTH_TYPE = "client_secret"
else:
    AUTH_TYPE = "public"

CLIENT_ID = (os.environ.get("CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.environ.get("CLIENT_SECRET") or "").strip()
# Default PBI / Power Platform public client (device sign-in) when AUTH_TYPE=public and CLIENT_ID unset.
_DEFAULT_PUBLIC_APP_ID = "23d8f6bd-1eb0-4cc2-a08c-7bf525c67bcd"
PUBLIC_CLIENT_ID = CLIENT_ID or _DEFAULT_PUBLIC_APP_ID

if AUTH_TYPE == "client_secret":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("\n  ERROR: AUTH_TYPE=client_secret requires CLIENT_ID and CLIENT_SECRET in the environment.\n")
        sys.exit(1)
else:
    if CLIENT_SECRET and not CLIENT_ID:
        print("\n  ERROR: CLIENT_SECRET is set; set AUTH_TYPE=client_secret and provide CLIENT_ID, or remove CLIENT_SECRET.\n")
        sys.exit(1)

# Power BI — same logical scope; device flow uses the delegated / default scope, CCA uses resource .default.
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]
# Fabric (delegated); CCA remaps to https://api.fabric.microsoft.com/.default in auth.get_token
FABRIC_DELEGATE_SCOPES = ["https://api.fabric.microsoft.com/Workspace.Read.All"]

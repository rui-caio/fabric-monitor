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

SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]
PUBLIC_CLIENT_ID = "23d8f6bd-1eb0-4cc2-a08c-7bf525c67bcd"

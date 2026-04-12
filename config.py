import os
import sys

def _load_env(path=None):
    """Carrega variáveis de um ficheiro .env para os.environ (sem dependências externas)."""
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

_missing = [k for k, v in {
    "TENANT_ID": TENANT_ID, "CAPACITY_ID": CAPACITY_ID,
    "METRICS_WS": METRICS_WS, "METRICS_DS": METRICS_DS,
}.items() if not v]
if _missing:
    print(f"\n  ERRO: variáveis não configuradas: {', '.join(_missing)}")
    print("  Copia .env.example para .env e preenche os valores.\n")
    sys.exit(1)

SCOPES           = ["https://analysis.windows.net/powerbi/api/.default"]
PUBLIC_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

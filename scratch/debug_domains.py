import sys
import os
import json

# Add current dir to path to import local modules
sys.path.append(os.getcwd())

from auth import get_token, call_api
from api.domains import FABRIC_SCOPE, FABRIC_BASE

def log(msg):
    print(msg, flush=True)

def debug_domains():
    log("--- DEBUG DOMAINS ---")
    try:
        log("Acquiring token...")
        token = get_token(FABRIC_SCOPE)
        log(f"Token acquired (length: {len(token)})")
        
        url = f"{FABRIC_BASE}/admin/domains"
        log(f"Calling: {url}")
        status, data = call_api(url, token)
        log(f"Status: {status}")
        
        if status != 200:
            log(f"Error data: {json.dumps(data, indent=2)}")
            return

        domains = data.get("domains", [])
        log(f"Found {len(domains)} domains.")
        
        for d in domains:
            d_id = d.get("id")
            d_name = d.get("displayName")
            log(f"  - Domain: {d_name} ({d_id})")
            
            ws_url = f"{FABRIC_BASE}/admin/domains/{d_id}/workspaces"
            log(f"    Fetching workspaces: {ws_url}")
            ws_status, ws_data = call_api(ws_url, token)
            log(f"    WS Status: {ws_status}")
            
            if ws_status == 200:
                wss = ws_data.get("value", [])
                log(f"    Found {len(wss)} workspaces in this domain.")
                for ws in wss[:5]: # Show first 5
                    log(f"      * {ws.get('name')} ({ws.get('id')})")
                if len(wss) > 5:
                    log("      ...")
            else:
                log(f"    Error fetching workspaces: {ws_data}")

    except Exception as e:
        log(f"DEBUG ERROR: {e}")

if __name__ == "__main__":
    debug_domains()

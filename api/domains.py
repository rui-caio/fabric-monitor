import json
import urllib.parse
from auth import get_token, call_api

FABRIC_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = ["https://api.fabric.microsoft.com/Workspace.Read.All"]

_domains_map = {} # workspace_id (guid) -> domain_name
_domains_by_name = {} # workspace_name (lower) -> domain_name

def get_domain_for_workspace(workspace_id=None, workspace_name=None):
    """Returns the Domain name for a given workspace ID or Name, or 'No Domain' if not found."""
    if workspace_id:
        val = _domains_map.get(str(workspace_id).strip().lower())
        if val: return val
    if workspace_name:
        val = _domains_by_name.get(str(workspace_name).strip().lower())
        if val: return val
    return "No Domain"

def load_domains_map():
    """Fetches all domains and their associated workspaces using the Fabric API."""
    global _domains_map, _domains_by_name
    print("  Domains: loading workspace-domain mapping...", flush=True)
    
    new_map = {}
    new_map_name = {}
    
    try:
        # Request the Fabric token explicitly. With persistent cache, this only prompts once ever.
        token = get_token(FABRIC_SCOPE) 
        if not token: return

        # Attempt 1: Admin API
        domains_url = f"{FABRIC_BASE}/admin/domains"
        status, data = call_api(domains_url, token)
        
        if status == 200:
            print("  Domains: using Admin API path...", flush=True)
            while domains_url:
                if status != 200: break
                domain_list = data.get("domains", [])
                for d in domain_list:
                    d_id, d_name = d.get("id"), d.get("displayName")
                    if not d_id or not d_name: continue
                    ws_url = f"{FABRIC_BASE}/admin/domains/{d_id}/workspaces"
                    while ws_url:
                        ws_status, ws_data = call_api(ws_url, token)
                        if ws_status != 200: break
                        wss = ws_data.get("workspaces", ws_data.get("value", []))
                        for ws in wss:
                            wid, wname = ws.get("id"), ws.get("name")
                            if wid: new_map[str(wid).strip().lower()] = d_name
                            if wname: new_map_name[str(wname).strip().lower()] = d_name
                        ws_url = ws_data.get("@odata.nextLink") or ws_data.get("continuationUri")
                domains_url = data.get("@odata.nextLink") or data.get("continuationUri")
                if domains_url: status, data = call_api(domains_url, token)
        else:
            # Attempt 2: Non-Admin Fallback
            print(f"  Domains: Admin API denied (HTTP {status}). Trying workspace-by-workspace fallback...", flush=True)
            ws_url = f"{FABRIC_BASE}/workspaces"
            domain_names_cache = {} # id -> name
            
            while ws_url:
                ws_status, ws_data = call_api(ws_url, token)
                if ws_status != 200: break
                
                for ws in ws_data.get("value", []):
                    wid, wname, did = ws.get("id"), ws.get("displayName"), ws.get("domainId")
                    if not wid or not did: continue
                    
                    # Resolve domain name if not in cache
                    if did not in domain_names_cache:
                        d_status, d_data = call_api(f"{FABRIC_BASE}/domains/{did}", token)
                        if d_status == 200:
                            domain_names_cache[did] = d_data.get("displayName") or "Unknown Domain"
                        else:
                            domain_names_cache[did] = "No Access to Domain Name"
                    
                    d_name = domain_names_cache[did]
                    new_map[str(wid).strip().lower()] = d_name
                    if wname: new_map_name[str(wname).strip().lower()] = d_name
                
                ws_url = ws_data.get("@odata.nextLink")
            
        _domains_map = new_map
        _domains_by_name = new_map_name
        print(f"  Domains: successfully loaded {len(_domains_map)} mappings.", flush=True)

    except Exception as e:
        print(f"  Domains: mapping failed: {e}", flush=True)



def get_domain_status():
    return {
        "workspaces_mapped": len(_domains_map),
        "status": "loaded" if _domains_map else "empty",
        "samples": list(_domains_by_name.items())[:5]
    }

"""
Inventory of Fabric / Power BI artefacts in workspaces assigned to the configured capacity.
Uses Fabric Core List Items when a Fabric token is available; otherwise Power BI REST.

Power BI admin mode uses tenant-wide Admin APIs (/admin/reports, etc.) with pagination
and in-memory filtering by workspace id — avoids per-workspace calls that trigger 429.
"""
import urllib.parse

from auth import get_token, try_fabric_token_silent, call_api
from config import CAPACITY_ID

PBI_BASE = "https://api.powerbi.com/v1.0/myorg"
FABRIC_BASE = "https://api.fabric.microsoft.com/v1"

# Max page size for admin list APIs (reduces number of HTTP calls vs small pages).
_ADMIN_PAGE_TOP = 5000


def _pbi_get_json_paged(url, token):
    rows = []
    while url:
        status, data = call_api(url, token)
        if status != 200:
            err = data.get("error") if isinstance(data, dict) else str(data)
            raise Exception(f"HTTP {status}: {err}")
        rows.extend(data.get("value") or [])
        url = data.get("@odata.nextLink")
    return rows


def _capacity_workspaces_non_admin(pbi_token):
    """
    Fallback when /admin/groups is forbidden: list workspaces the user can access
    and keep those whose capacityId matches CAPACITY_ID (property present for Premium/Fabric).
    Returns (workspaces, "user") — artefact APIs must use /groups/... (caller has access).
    """
    cap_lc = CAPACITY_ID.lower()
    out = []
    url = f"{PBI_BASE}/groups?$top=5000"
    while url:
        status, data = call_api(url, pbi_token)
        if status != 200:
            err = data.get("error") if isinstance(data, dict) else str(data)
            raise Exception(f"Groups HTTP {status}: {err}")
        for w in data.get("value") or []:
            cid = w.get("capacityId")
            if not cid or str(cid).lower() != cap_lc:
                continue
            wid = w.get("id")
            if wid:
                out.append({"id": wid, "name": w.get("name") or ""})
        url = data.get("@odata.nextLink")
    return out, "user"


def _capacity_workspaces(pbi_token):
    """
    Workspaces assigned to CAPACITY_ID.
    Uses Admin API (recommended): GET /admin/groups?$filter=capacityId eq '{id}'.
    Returns (workspaces, "admin" | "user") so callers use matching artefact APIs.
    """
    filt = f"capacityId eq '{CAPACITY_ID}'"
    url = (
        f"{PBI_BASE}/admin/groups?$top=5000"
        f"&$filter={urllib.parse.quote(filt)}"
    )
    out = []
    first = True
    while url:
        status, data = call_api(url, pbi_token)
        if status != 200:
            if first and status == 403:
                print("  Inventory: admin/groups forbidden — falling back to /groups + capacityId filter")
                return _capacity_workspaces_non_admin(pbi_token)
            err = data.get("error") if isinstance(data, dict) else str(data)
            raise Exception(f"Capacity workspaces HTTP {status}: {err}")
        first = False
        for w in data.get("value") or []:
            wid = w.get("id")
            if wid:
                out.append({"id": wid, "name": w.get("name") or ""})
        url = data.get("@odata.nextLink")
    return out, "admin"


def _fabric_items_for_workspace(fabric_token, workspace_id, workspace_name):
    items = []
    base = f"{FABRIC_BASE}/workspaces/{urllib.parse.quote(workspace_id)}/items"
    path = f"{base}?recursive=true"
    cont = None
    while True:
        url = path
        if cont is not None:
            url = f"{base}?recursive=true&continuationToken={urllib.parse.quote(cont, safe='')}"
        status, data = call_api(url, fabric_token)
        if status != 200:
            err = data.get("error") if isinstance(data, dict) else str(data)
            return None, f"HTTP {status}: {err}"
        for it in data.get("value") or []:
            items.append({
                "workspaceId": workspace_id,
                "workspaceName": workspace_name,
                "itemId": it.get("id") or "",
                "name": it.get("displayName") or "",
                "type": it.get("type") or "Unknown",
                "description": (it.get("description") or "")[:500],
            })
        cont = data.get("continuationToken")
        if not cont:
            break
    return items, None


def _pbi_artifacts_for_workspace(pbi_token, workspace_id, workspace_name, warnings, use_admin_api):
    """
    Per-workspace listing (used when workspace list came from non-admin /groups).
    """
    out = []
    gid = urllib.parse.quote(workspace_id)
    base = f"{PBI_BASE}/admin/groups/{gid}" if use_admin_api else f"{PBI_BASE}/groups/{gid}"
    specs = [
        ("reports", "Report", "name"),
        ("datasets", "Dataset", "name"),
        ("dashboards", "Dashboard", "displayName"),
        ("dataflows", "Dataflow", "name"),
    ]
    for path, typ, name_field in specs:
        url = f"{base}/{path}"
        try:
            for r in _pbi_get_json_paged(url, pbi_token):
                name = r.get(name_field) or r.get("name") or ""
                item_id = (r.get("objectId") or r.get("id") or "") if path == "dataflows" else (r.get("id") or "")
                out.append({
                    "workspaceId": workspace_id,
                    "workspaceName": workspace_name,
                    "itemId": item_id,
                    "name": name,
                    "type": typ,
                    "description": "",
                })
        except Exception as e:
            warnings.append(f"{workspace_name} · {path}: {e}")
    return out


def _pbi_artifacts_bulk_admin(pbi_token, workspaces_subset, warnings):
    """
    Single paginated scan per artefact type across the tenant (GetXxxAsAdmin),
    keep rows whose workspaceId is in the capacity workspace set.
    Few HTTP calls vs one per workspace per type (avoids 429 from per-group admin calls).
    """
    if not workspaces_subset:
        return []

    ws_set = {str(w["id"]).lower() for w in workspaces_subset}
    ws_name = {str(w["id"]).lower(): (w.get("name") or "") for w in workspaces_subset}
    out = []

    streams = [
        ("admin/reports", "Report", lambda r: r.get("name") or "", lambda r: r.get("id") or ""),
        ("admin/datasets", "Dataset", lambda r: r.get("name") or "", lambda r: r.get("id") or ""),
        ("admin/dashboards", "Dashboard", lambda r: r.get("displayName") or r.get("name") or "", lambda r: r.get("id") or ""),
        ("admin/dataflows", "Dataflow", lambda r: r.get("name") or "", lambda r: r.get("objectId") or r.get("id") or ""),
    ]

    for path_prefix, typ, get_name, get_id in streams:
        url = f"{PBI_BASE}/{path_prefix}?$top={_ADMIN_PAGE_TOP}"
        page = 0
        while url:
            status, data = call_api(url, pbi_token)
            page += 1
            if status != 200:
                err = data.get("error") if isinstance(data, dict) else str(data)
                if isinstance(err, dict):
                    err = err.get("message", err)
                warnings.append(f"{path_prefix} (page {page}): HTTP {status}: {err}")
                break
            for r in data.get("value") or []:
                wsid = r.get("workspaceId")
                if not wsid or str(wsid).lower() not in ws_set:
                    continue
                wkey = str(wsid).lower()
                out.append({
                    "workspaceId": wsid,
                    "workspaceName": ws_name.get(wkey, ""),
                    "itemId": get_id(r),
                    "name": get_name(r),
                    "type": typ,
                    "description": "",
                })
            url = data.get("@odata.nextLink")

    return out


def handle_inventory(payload):
    _ = payload
    pbi_token = get_token()
    workspaces, ws_list_mode = _capacity_workspaces(pbi_token)
    use_admin_artifacts = ws_list_mode == "admin"
    print(f"  Inventory: {len(workspaces)} workspaces on capacity (artifact API: {'admin' if use_admin_artifacts else 'user'})")

    fabric_token = try_fabric_token_silent()
    if not fabric_token:
        print(
            "  Inventory: no cached Fabric token (Workspace.Read.All) — "
            "using Power BI API only (reports, datasets, dashboards, dataflows)."
        )

    items = []
    warnings = []
    fabric_ok_ids = set()

    if fabric_token:
        for ws in workspaces:
            wid, wname = ws["id"], ws["name"]
            witems, err = _fabric_items_for_workspace(fabric_token, wid, wname)
            if err is None:
                items.extend(witems)
                fabric_ok_ids.add(str(wid).lower())
            else:
                warnings.append(f"{wname} (Fabric): {err}")

    need_pbi = [w for w in workspaces if str(w["id"]).lower() not in fabric_ok_ids]

    if need_pbi:
        if use_admin_artifacts:
            print(f"  Inventory: bulk admin scan for {len(need_pbi)} workspace(s) needing Power BI REST…")
            items.extend(_pbi_artifacts_bulk_admin(pbi_token, need_pbi, warnings))
        else:
            for ws in need_pbi:
                items.extend(
                    _pbi_artifacts_for_workspace(
                        pbi_token, ws["id"], ws["name"], warnings, use_admin_api=False
                    )
                )

    fabric_ok = len(fabric_ok_ids)
    powerbi_ok = len(need_pbi)

    if fabric_ok and need_pbi:
        source = "mixed"
    elif fabric_ok and not need_pbi:
        source = "fabric"
    else:
        source = "powerbi"

    counts = {}
    for it in items:
        t = it.get("type") or "Unknown"
        counts[t] = counts.get(t, 0) + 1

    print(f"  Inventory: {len(items)} items ({source}; fabric_ws={fabric_ok}, pbi_ws={powerbi_ok})")
    return {
        "items": items,
        "workspaces": workspaces,
        "countsByType": counts,
        "source": source,
        "warnings": warnings,
    }

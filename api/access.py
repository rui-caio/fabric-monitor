"""
Access Explorer — workspace / dataset / user permissions via Power BI Admin APIs.
Scoped to workspaces on the configured Fabric capacity.
"""
import json
import os
import time
import urllib.parse

from auth import get_token, call_api
from api.inventory import _capacity_workspaces
from api.domains import get_domain_for_workspace

PBI_BASE = "https://api.powerbi.com/v1.0/myorg"
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_BASE_DIR, ".cache", "access")
_CACHE_TTL_SEC = 86400  # 24h — admin permission APIs are rate-limited (~200/hr per endpoint)


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(key):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _cache_read(key):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if time.time() - blob.get("cachedAt", 0) > _CACHE_TTL_SEC:
            return None
        return blob.get("data")
    except Exception:
        return None


def _cache_write(key, data):
    _ensure_cache_dir()
    with open(_cache_path(key), "w", encoding="utf-8") as f:
        json.dump({"cachedAt": time.time(), "data": data}, f, ensure_ascii=False)


def _capacity_context(pbi_token):
    workspaces, mode = _capacity_workspaces(pbi_token)
    ws_set = {str(w["id"]).lower() for w in workspaces}
    ws_name = {str(w["id"]).lower(): w.get("name") or "" for w in workspaces}
    return workspaces, ws_set, ws_name, mode


def _api_error(status, data):
    err = data.get("error") if isinstance(data, dict) else str(data)
    if isinstance(err, dict):
        err = err.get("message") or err.get("code") or str(err)
    return f"HTTP {status}: {err}"


def _api_get_value(url, pbi_token):
    status, data = call_api(url, pbi_token)
    if status == 429:
        raise Exception(
            "HTTP 429: Power BI admin API rate limit. Wait and retry, or use cached results."
        )
    if status != 200:
        raise Exception(_api_error(status, data))
    return data.get("value") or []


def _fetch_user_artifact_pages(pbi_token, user_id, types):
    """
    Paginate GetUserArtifactAccessAsAdmin.
    Prefer continuationUri from the API (avoids mis-encoding continuationToken).
    """
    uid = urllib.parse.quote(user_id, safe="")
    base = f"{PBI_BASE}/admin/users/{uid}/artifactAccess"
    url = f"{base}?{urllib.parse.urlencode({'artifactTypes': ','.join(types)})}"
    entries_raw = []
    while url:
        status, data = call_api(url, pbi_token)
        if status == 429:
            raise Exception(
                "HTTP 429: Power BI admin API rate limit. Wait and retry, or use cached results."
            )
        if status != 200:
            raise Exception(_api_error(status, data))
        entries_raw.extend(
            data.get("ArtifactAccessEntities")
            or data.get("artifactAccessEntities")
            or data.get("artifactAccessEntries")
            or data.get("value")
            or []
        )
        next_uri = (data.get("continuationUri") or "").strip()
        if next_uri:
            # Use API-provided URL as-is (token quoting is already in the query string).
            url = next_uri
            continue
        cont = (data.get("continuationToken") or "").strip().strip("'\"")
        if not cont:
            break
        # Single urlencode pass — do not urllib.parse.quote() the token again.
        url = f"{base}?{urllib.parse.urlencode({'artifactTypes': ','.join(types), 'continuationToken': cont})}"
    return entries_raw


def _artifact_workspace_maps(pbi_token, ws_set=None):
    """
    itemId (lower) -> {workspaceId, workspaceName, name, type}.
    ws_set=None: tenant-wide (all workspaces). Otherwise filter to those workspace ids.
    """
    maps = {}
    streams = [
        ("admin/datasets", "Dataset", lambda r: r.get("id"), lambda r: r.get("name")),
        ("admin/reports", "Report", lambda r: r.get("id"), lambda r: r.get("name")),
        ("admin/dashboards", "Dashboard", lambda r: r.get("id"), lambda r: r.get("displayName") or r.get("name")),
        ("admin/dataflows", "Dataflow", lambda r: r.get("objectId") or r.get("id"), lambda r: r.get("name")),
    ]
    for prefix, typ, get_id, get_name in streams:
        url = f"{PBI_BASE}/{prefix}?$top=5000"
        try:
            while url:
                status, data = call_api(url, pbi_token)
                if status != 200:
                    break
                for r in data.get("value") or []:
                    wsid = r.get("workspaceId")
                    if not wsid:
                        continue
                    if ws_set is not None and str(wsid).lower() not in ws_set:
                        continue
                    iid = get_id(r)
                    if not iid:
                        continue
                    key = str(iid).lower()
                    wn = r.get("workspaceName") or ""
                    maps[key] = {
                        "workspaceId": wsid,
                        "workspaceName": wn,
                        "name": get_name(r) or "",
                        "type": typ,
                    }
                url = data.get("@odata.nextLink")
        except Exception:
            pass
    return maps


def _normalize_user_row(row, access_field):
    right = row.get(access_field) or row.get("datasetUserAccessRight") or row.get("groupUserAccessRight") or ""
    return {
        "displayName": row.get("displayName") or "",
        "emailAddress": row.get("emailAddress") or "",
        "identifier": row.get("identifier") or "",
        "graphId": row.get("graphId") or "",
        "principalType": row.get("principalType") or "",
        "userType": row.get("userType") or "",
        "accessRight": right,
    }


def handle_access_catalog(payload):
    _ = payload
    pbi_token = get_token()
    workspaces, ws_set, ws_name, mode = _capacity_context(pbi_token)
    cache_key = "catalog_v1"
    cached = _cache_read(cache_key)
    if cached and cached.get("workspaceCount") == len(workspaces):
        return {**cached, "fromCache": True}

    datasets = []
    url = f"{PBI_BASE}/admin/datasets?$top=5000"
    while url:
        status, data = call_api(url, pbi_token)
        if status != 200:
            err = data.get("error") if isinstance(data, dict) else str(data)
            if isinstance(err, dict):
                err = err.get("message") or str(err)
            raise Exception(f"Datasets catalog HTTP {status}: {err}")
        for r in data.get("value") or []:
            wsid = r.get("workspaceId")
            if not wsid or str(wsid).lower() not in ws_set:
                continue
            did = r.get("id")
            if not did:
                continue
            wkey = str(wsid).lower()
            wn = ws_name.get(wkey) or r.get("workspaceName") or ""
            datasets.append({
                "id": did,
                "name": r.get("name") or "",
                "workspaceId": wsid,
                "workspaceName": wn,
                "domain": get_domain_for_workspace(workspace_id=wsid, workspace_name=wn),
            })
        url = data.get("@odata.nextLink")

    out = {
        "workspaces": workspaces,
        "datasets": datasets,
        "workspaceCount": len(workspaces),
        "datasetCount": len(datasets),
        "listMode": mode,
        "fromCache": False,
    }
    _cache_write(cache_key, out)
    print(f"  Access catalog: {len(workspaces)} workspaces, {len(datasets)} datasets")
    return out


def handle_dataset_users(payload):
    dataset_id = (payload.get("datasetId") or "").strip()
    if not dataset_id:
        raise Exception("datasetId is required")
    refresh = bool(payload.get("refresh"))
    cache_key = f"ds_users_{dataset_id.lower()}"
    if not refresh:
        cached = _cache_read(cache_key)
        if cached is not None:
            return {**cached, "fromCache": True}

    pbi_token = get_token()
    gid = urllib.parse.quote(dataset_id)
    url = f"{PBI_BASE}/admin/datasets/{gid}/users"
    users_raw = _api_get_value(url, pbi_token)
    users = [_normalize_user_row(u, "datasetUserAccessRight") for u in users_raw]
    out = {
        "datasetId": dataset_id,
        "users": users,
        "count": len(users),
        "fromCache": False,
    }
    _cache_write(cache_key, out)
    print(f"  Access: dataset {dataset_id[:8]}… → {len(users)} principals")
    return out


def handle_workspace_users(payload):
    workspace_id = (payload.get("workspaceId") or "").strip()
    if not workspace_id:
        raise Exception("workspaceId is required")
    refresh = bool(payload.get("refresh"))
    cache_key = f"ws_users_{workspace_id.lower()}"
    if not refresh:
        cached = _cache_read(cache_key)
        if cached is not None:
            return {**cached, "fromCache": True}

    pbi_token = get_token()
    _, ws_set, ws_name, mode = _capacity_context(pbi_token)
    if str(workspace_id).lower() not in ws_set:
        raise Exception("Workspace is not on the configured capacity")

    gid = urllib.parse.quote(workspace_id)
    if mode == "admin":
        url = f"{PBI_BASE}/admin/groups/{gid}/users"
    else:
        url = f"{PBI_BASE}/groups/{gid}/users"
    users_raw = _api_get_value(url, pbi_token)
    users = [_normalize_user_row(u, "groupUserAccessRight") for u in users_raw]
    wn = ws_name.get(str(workspace_id).lower()) or ""
    out = {
        "workspaceId": workspace_id,
        "workspaceName": wn,
        "users": users,
        "count": len(users),
        "fromCache": False,
    }
    _cache_write(cache_key, out)
    print(f"  Access: workspace {wn or workspace_id[:8]}… → {len(users)} principals")
    return out


def handle_user_artifacts(payload):
    user_id = (payload.get("userId") or "").strip()
    if not user_id:
        raise Exception("userId is required (UPN or Azure AD object id)")
    refresh = bool(payload.get("refresh"))
    types = payload.get("artifactTypes") or ["Dataset"]
    if isinstance(types, str):
        types = [t.strip() for t in types.split(",") if t.strip()]
    types_key = "-".join(sorted(types))
    # v2 = tenant-wide (no capacity filter)
    cache_key = f"user_art_tenant_v2_{urllib.parse.quote(user_id, safe='')}__{types_key}"
    if not refresh:
        cached = _cache_read(cache_key)
        if cached is not None:
            return {**cached, "fromCache": True}

    pbi_token = get_token()
    _, ws_set, ws_name, _ = _capacity_context(pbi_token)
    entries_raw = _fetch_user_artifact_pages(pbi_token, user_id, types)

    # Tenant-wide map to resolve workspace names (not limited to configured capacity).
    item_map = _artifact_workspace_maps(pbi_token, ws_set=None)
    entries = []
    unresolved_workspace = 0
    for row in entries_raw:
        aid = row.get("artifactId") or row.get("id") or ""
        meta = item_map.get(str(aid).lower()) if aid else None
        wsid = (meta or {}).get("workspaceId") or ""
        wkey = str(wsid).lower() if wsid else ""
        wn = (meta or {}).get("workspaceName") or (ws_name.get(wkey) if wkey else "") or ""
        if aid and not meta:
            unresolved_workspace += 1
        on_cap = bool(wkey and wkey in ws_set)
        entries.append({
            "artifactId": aid,
            "artifactType": row.get("artifactType") or (meta or {}).get("type") or "",
            "artifactName": row.get("displayName") or (meta or {}).get("name") or "",
            "accessRight": row.get("artifactAccessRight") or row.get("accessRight") or "",
            "workspaceId": wsid,
            "workspaceName": wn,
            "domain": get_domain_for_workspace(workspace_id=wsid, workspace_name=wn) if wsid else "",
            "onConfiguredCapacity": on_cap,
        })

    out = {
        "userId": user_id,
        "artifactTypes": types,
        "entries": entries,
        "count": len(entries),
        "unresolvedWorkspace": unresolved_workspace,
        "scope": "tenant",
        "fromCache": False,
    }
    _cache_write(cache_key, out)
    print(
        f"  Access: user {user_id[:40]}… → {len(entries)} tenant items"
        + (f" ({unresolved_workspace} without workspace metadata)" if unresolved_workspace else "")
    )
    return out

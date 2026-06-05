import concurrent.futures
import gzip
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from auth import get_token, call_api
from config import CAPACITY_ID

_CACHE_DIR  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.cache', 'datasources')
_CACHE_FILE = os.path.join(_CACHE_DIR, 'datasources.json.gz')
_CACHE_TTL_H = 24


def _load_cache():
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        if (time.time() - os.path.getmtime(_CACHE_FILE)) / 3600 > _CACHE_TTL_H:
            return None
        with gzip.open(_CACHE_FILE, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(data):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with gzip.open(_CACHE_FILE, 'wt', encoding='utf-8') as f:
        json.dump(data, f)


def _call(url, token, method='GET', body=None):
    headers = {'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def _get_workspace_ids(token):
    import urllib.parse
    filt = f"capacityId eq '{CAPACITY_ID}'"
    url = (f"https://api.powerbi.com/v1.0/myorg/admin/groups?$top=5000"
           f"&$filter={urllib.parse.quote(filt)}")
    ids = []
    while url:
        status, data = call_api(url, token)
        if status != 200:
            break
        for w in data.get('value') or []:
            wid = w.get('id')
            if not wid:
                continue
            if w.get('type') in ('PersonalGroup',):
                continue
            if w.get('state') and w.get('state') != 'Active':
                continue
            ids.append(wid)
        url = data.get('@odata.nextLink')
    if ids:
        return ids
    status, data = call_api("https://api.powerbi.com/v1.0/myorg/groups?$top=5000", token)
    if status == 200:
        return [g['id'] for g in data.get('value', []) if g.get('capacityId') == CAPACITY_ID]
    return []


def _get_workspace_dataset_ids(args):
    """GET /admin/groups/{wsId}/datasets — returns list of dataset IDs."""
    token, ws_id = args
    url = f"https://api.powerbi.com/v1.0/myorg/admin/groups/{ws_id}/datasets"
    for attempt in range(3):
        status, data = _call(url, token)
        if status == 200:
            return [ds['id'] for ds in data.get('value', []) if ds.get('id')]
        if status == 429:
            time.sleep(5 * (attempt + 1))
            continue
        break
    return []


def _fetch_datasources(args):
    """GET /admin/datasets/{id}/datasources — returns (id, sources|None)."""
    token, dataset_id = args
    url = f"https://api.powerbi.com/v1.0/myorg/admin/datasets/{dataset_id}/datasources"
    for attempt in range(3):
        status, data = _call(url, token)
        if status == 200:
            sources = []
            for ds in data.get('value', []):
                conn = ds.get('connectionDetails') or {}
                src = {
                    'type':     ds.get('datasourceType', ''),
                    'server':   conn.get('server', ''),
                    'database': conn.get('database', ''),
                    'url':      conn.get('url', ''),
                    'path':     conn.get('path', ''),
                }
                if src not in sources:
                    sources.append(src)
            return dataset_id.lower(), sources or None
        if status == 429:
            time.sleep(5 * (attempt + 1))
            continue
        break
    return dataset_id.lower(), None


def handle_datasources(payload):
    if not payload.get('refresh'):
        cached = _load_cache()
        if cached:
            print(f"  Datasources: cache hit ({cached.get('dataset_count', 0)} datasets)")
            return cached

    token = get_token()

    print("  Datasources: fetching workspace IDs...")
    ws_ids = _get_workspace_ids(token)
    if not ws_ids:
        return {'by_dataset': {}, 'workspace_count': 0, 'dataset_count': 0}
    print(f"  Datasources: {len(ws_ids)} workspaces — collecting dataset IDs...")

    # Step 1: collect all dataset IDs from all workspaces (parallel)
    all_dataset_ids = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for ids in ex.map(_get_workspace_dataset_ids, [(token, ws_id) for ws_id in ws_ids]):
            all_dataset_ids.extend(ids)

    dataset_ids = list(dict.fromkeys(all_dataset_ids))
    print(f"  Datasources: {len(dataset_ids)} datasets — fetching datasources (10 parallel)...")

    # Step 2: fetch datasources for each dataset (parallel)
    by_dataset = {}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for ds_id, sources in ex.map(_fetch_datasources, [(token, i) for i in dataset_ids]):
            done += 1
            if sources:
                by_dataset[ds_id] = sources
            if done % 100 == 0:
                print(f"  Datasources: {done}/{len(dataset_ids)} processed, {len(by_dataset)} with sources")

    output = {
        'by_dataset':      by_dataset,
        'workspace_count': len(ws_ids),
        'dataset_count':   len(by_dataset),
        'scanned_at':      datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(output)
    print(f"  Datasources: done — {len(by_dataset)}/{len(dataset_ids)} datasets com source info")
    return output

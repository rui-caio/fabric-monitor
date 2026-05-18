import json
import math
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from auth import get_token, call_api
from config import DISPLAY_TIMEZONE, DISPLAY_UTC_OFFSET_HOURS

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_BASE_DIR, '.cache', 'activityevents')
os.makedirs(_CACHE_DIR, exist_ok=True)

import time
_LAST_CLEANUP_TIME = 0

def _cleanup_old_cache(days_to_keep=32):
    global _LAST_CLEANUP_TIME
    now = time.time()
    # Run cleanup at most once per hour to avoid disk overhead
    if now - _LAST_CLEANUP_TIME < 3600:
        return
    _LAST_CLEANUP_TIME = now
    
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    try:
        for f in os.listdir(_CACHE_DIR):
            if not f.startswith('activity-') or not f.endswith('.json'):
                continue
            # Extract end date part: activity-YYYYMMDDTHHMMSSZ_YYYYMMDDTHHMMSSZ.json
            parts = f.replace('.json', '').split('_')
            if len(parts) == 2:
                try:
                    end_str = parts[1].replace('Z', '+0000')
                    end_dt = datetime.strptime(end_str, '%Y%m%dT%H%M%S%z')
                    if end_dt < cutoff_dt:
                        os.remove(os.path.join(_CACHE_DIR, f))
                except Exception:
                    pass
    except Exception as e:
        print(f"Error during cache cleanup: {e}")



def _cache_path(start_dt, end_dt):
    return os.path.join(
        _CACHE_DIR,
        f"activity-{start_dt.strftime('%Y%m%dT%H%M%SZ')}_{end_dt.strftime('%Y%m%dT%H%M%SZ')}.json"
    )


def _load_chunk(start_dt, end_dt):
    path = _cache_path(start_dt, end_dt)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def _save_chunk(start_dt, end_dt, events):
    path = _cache_path(start_dt, end_dt)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False)


def _event_ts_ms(e):
    ct = e.get('CreationTime')
    if ct is None:
        return None
    if isinstance(ct, (int, float)):
        return int(ct)
    s = str(ct).replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _snap_activity_window_utc(start_dt, end_dt):
    """Align to UTC hour boundaries so hourly chunk cache filenames match across refreshes."""
    su = start_dt.astimezone(timezone.utc)
    eu = end_dt.astimezone(timezone.utc)
    start_snap = su.replace(minute=0, second=0, microsecond=0)
    end_floor = eu.replace(minute=0, second=0, microsecond=0)
    if eu > end_floor:
        end_snap = end_floor + timedelta(hours=1)
    else:
        end_snap = end_floor
    return start_snap, end_snap


def _event_in_requested_range(e, req_start, req_end):
    """Keep events whose CreationTime falls in [req_start, req_end] (inclusive)."""
    t = _event_ts_ms(e)
    if t is None:
        return False
    ts = t / 1000.0
    return req_start.timestamp() <= ts <= req_end.timestamp()


def _activity_op(e):
    return e.get('Activity') or e.get('OperationName') or ''

def _is_success(e):
    if e.get('IsSuccess') is False: return False
    if str(e.get('ResultStatus', '')).lower() == 'failed': return False
    if str(e.get('ItemState', '')).lower() == 'failed': return False
    if str(e.get('Status', '')).lower() == 'failed': return False
    return True

def _clean_app_name(e):
    name = str(e.get('AppName') or e.get('UserAgent') or '')
    if not name: return ''
    if name.startswith('Power BI Desktop') or name == 'PBIDesktop.exe': return 'Power BI Desktop'
    if name.startswith('Power%20BI/') or name.startswith('Power BI/'): return 'Power BI App (Apple)'
    if name.startswith('DAX Studio'): return 'DAX Studio'
    if name.startswith('Tabular Editor') or name.startswith('TabularEditor-'): return 'Tabular Editor'
    if name.startswith('Bravo-'): return 'Bravo'
    if name.startswith('OneOutlook') or name.startswith('Win32_Outlook') or name.startswith('WAC_Outlook') or name.startswith('Outlook-'): return 'Outlook'
    if name.startswith('Microsoft Fabric Capacity Metrics'): return 'Microsoft Fabric Capacity Metrics'
    if name.startswith('Microsoft 365 Usage Analytics'): return 'Microsoft 365 Usage Analytics'
    if 'TeamsMobile-iOS' in name: return 'Teams Mobile (iOS)'
    if 'TeamsMobile-Android' in name: return 'Teams Mobile (Android)'
    if '[PBIMobile' in name or name.startswith('PBIMobile/'): return 'Power BI Mobile App'
    if 'SharePoint for Android' in name: return 'SharePoint Mobile App'
    if name.startswith('Mozilla/'):
        if 'Edg/' in name or 'EdgA/' in name or 'EdgiOS/' in name: return 'Edge Browser'
        if 'Chrome/' in name or 'CriOS/' in name: return 'Chrome Browser'
        if 'Firefox/' in name or 'FxiOS/' in name: return 'Firefox Browser'
        if 'Safari/' in name and 'Chrome' not in name: return 'Safari Browser'
        return 'Web Browser'
    if 'MicrosoftPowerBIMgmt' in name: return 'Power BI PowerShell Mgmt'
    if name.startswith('OneLakeClient'): return 'OneLake Client'
    if name.startswith('FxVersion/'): return 'Power BI .NET Client'
    if name.startswith('azure-logic-apps') or 'microsoft-flow' in name: return 'Power Automate / Logic Apps'
    if name.startswith('MSOLAP') or name == 'Excel' or name == 'EXCEL.EXE': return 'Excel / MSOLAP'
    if name.startswith('Microsoft SQL Server Management Studio'): return 'SQL Server Management Studio'
    if name.startswith('azsdk-python') or name.startswith('python-') or name.startswith('Python-'): return 'Python Script'
    if name.startswith('azsdk-net'): return '.NET Azure SDK'
    if name.startswith('okhttp'): return 'Java App (OkHttp)'
    if name.startswith('node-fetch'): return 'Node.js Script'
    if name.startswith('object_store/'): return 'Object Store Client'
    return name


def _display_hour_from_utc_dt(dt_utc):
    """Hour 0–23 for hour-of-day chart; matches web UI (timezone or fixed offset)."""
    if DISPLAY_TIMEZONE and ZoneInfo:
        try:
            return dt_utc.astimezone(ZoneInfo(DISPLAY_TIMEZONE)).hour
        except Exception:
            pass
    if DISPLAY_UTC_OFFSET_HOURS is not None:
        adj = dt_utc + timedelta(hours=DISPLAY_UTC_OFFSET_HOURS)
        return adj.astimezone(timezone.utc).hour
    return dt_utc.hour


def _method_label(e):
    m = e.get('ConsumptionMethod') or ''
    if m:
        return m
    ua = e.get('UserAgent') or ''
    if 'MSOLAP' in ua:
        return 'Power BI Desktop'
    if 'Excel' in ua:
        return 'Excel'
    if 'Azure' in ua:
        return 'Azure Client'
    if 'Mozil' in ua:
        return 'Web Browser'
    if ua == '':
        return 'System/API'
    return 'Other'


def _top_n_pairs(events, key_fn, n=15):
    counts = {}
    for ev in events:
        k = key_fn(ev)
        if k:
            counts[k] = counts.get(k, 0) + 1
    return [[a, b] for a, b in sorted(counts.items(), key=lambda x: -x[1])[:n]]


def _compute_chart_aggregates(events, max_buckets=48):
    empty = {
        'timeline': {
            'bucketStarts': [],
            'viewReport': [],
            'refresh': [],
            'external': [],
            'other': [],
        },
        'hourOfDay': [0] * 24,
        'method': {'labels': [], 'values': []},
        'artifact': {'labels': [], 'values': []},
        'operation': {'labels': [], 'values': []},
        'rankings': {
            'reports': [],
            'datasets': [],
            'users': [],
            'workspaces': [],
            'fails': [],
            'external': [],
        },
    }
    if not events:
        return empty

    times = [_event_ts_ms(e) for e in events]
    times = [t for t in times if t and t > 0]
    if not times:
        return empty

    min_t = min(times)
    max_t = max(times)
    range_ms = max(max_t - min_t, 1)
    n = min(max_buckets, max(1, math.ceil(range_ms / 3600000)))

    vr = [0] * n
    rf = [0] * n
    ex = [0] * n
    ot = [0] * n
    bucket_starts = [int(min_t + (range_ms * i) / n) for i in range(n)]

    for e in events:
        t = _event_ts_ms(e)
        if not t or t <= 0:
            continue
        t = max(min_t, min(max_t, t))
        idx = int((t - min_t) * n / range_ms)
        if idx >= n:
            idx = n - 1
        if idx < 0:
            idx = 0
        op = _activity_op(e)
        if op == 'ViewReport':
            vr[idx] += 1
        elif op == 'RefreshDataset':
            rf[idx] += 1
        elif op == 'ConnectFromExternalApplication':
            ex[idx] += 1
        else:
            ot[idx] += 1

    hod = [0] * 24
    for e in events:
        t = _event_ts_ms(e)
        if not t or t <= 0:
            continue
        dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        h = _display_hour_from_utc_dt(dt)
        if 0 <= h < 24:
            hod[h] += 1

    method_counts = {}
    for e in events:
        lab = _method_label(e)
        method_counts[lab] = method_counts.get(lab, 0) + 1
    method_sorted = sorted(method_counts.items(), key=lambda x: -x[1])
    method_labels = [x[0] for x in method_sorted]
    method_vals = [x[1] for x in method_sorted]

    art_counts = {}
    for e in events:
        k = e.get('ArtifactKind') or e.get('ObjectType') or 'Other'
        art_counts[k] = art_counts.get(k, 0) + 1
    art_sorted = sorted(art_counts.items(), key=lambda x: -x[1])
    art_labels = [x[0] for x in art_sorted]
    art_vals = [x[1] for x in art_sorted]

    op_counts = {}
    for e in events:
        op = _activity_op(e) or 'Other'
        op_counts[op] = op_counts.get(op, 0) + 1
    op_sorted = sorted(op_counts.items(), key=lambda x: -x[1])[:12]
    op_labels = [x[0] for x in op_sorted]
    op_vals = [x[1] for x in op_sorted]

    failed = [e for e in events if not _is_success(e)]
    ext_only = [e for e in events if _activity_op(e) == 'ConnectFromExternalApplication']

    return {
        'timeline': {
            'bucketStarts': bucket_starts,
            'viewReport': vr,
            'refresh': rf,
            'external': ex,
            'other': ot,
        },
        'hourOfDay': hod,
        'method': {'labels': method_labels, 'values': method_vals},
        'artifact': {'labels': art_labels, 'values': art_vals},
        'operation': {'labels': op_labels, 'values': op_vals},
        'rankings': {
            'reports': _top_n_pairs(
                events,
                lambda e: e.get('ReportName') or e.get('ArtifactName') or '',
                15,
            ),
            'datasets': _top_n_pairs(events, lambda e: e.get('DatasetName') or '', 15),
            'users': _top_n_pairs(
                events,
                lambda e: e.get('UserId') or e.get('UserName') or '',
                15,
            ),
            'workspaces': _top_n_pairs(
                events,
                lambda e: e.get('WorkSpaceName') or e.get('WorkspaceName') or '',
                15,
            ),
            'fails': _top_n_pairs(failed, lambda e: _activity_op(e) or '', 10),
            'external': _top_n_pairs(
                ext_only,
                lambda e: _clean_app_name(e) or 'Unknown app',
                10,
            ),
        },
    }


def handle_activity(payload):
    _cleanup_old_cache()
    token = get_token()

    start_str = payload.get("start")
    end_str   = payload.get("end")

    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc) - timedelta(hours=1)
    end_dt   = datetime.fromisoformat(end_str.replace("Z",   "+00:00")) if end_str   else datetime.now(timezone.utc)

    request_start = start_dt
    request_end = end_dt

    def _fetch_chunk(chunk_start, chunk_end, auth_token):
        fmt = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        s = fmt(chunk_start)
        e = fmt(chunk_end)
        params = {
            "startDateTime": f"'{s}'",
            "endDateTime": f"'{e}'",
        }
        url = f"https://api.powerbi.com/v1.0/myorg/admin/activityevents?{urlencode(params)}"

        print(f"  Chunk: {s} → {e}")
        events = []
        while url:
            status, data = call_api(url, auth_token)
            if status != 200:
                err = data.get("error", data.get("message", str(data)))
                raise Exception(f"Activity API erro {status}: {err}")
            page_events = data.get("activityEventEntities", [])
            events.extend(page_events)
            url = data.get("continuationUri") or data.get("@odata.nextLink")
        return events

    def _load_activity_range(range_start, range_end, auth_token):
        events = []
        cursor = range_start

        while cursor < range_end:
            end_of_day = cursor.replace(hour=23, minute=59, second=59, microsecond=0)
            chunk_end = min(range_end, cursor + timedelta(hours=1), end_of_day)

            cached_events = _load_chunk(cursor, chunk_end)
            if cached_events is not None:
                print(f"  Cache hit: {cursor.isoformat()} → {chunk_end.isoformat()} ({len(cached_events)} events)")
                events.extend(cached_events)
            else:
                events_chunk = _fetch_chunk(cursor, chunk_end, auth_token)
                _save_chunk(cursor, chunk_end, events_chunk)
                events.extend(events_chunk)

            cursor = chunk_end if chunk_end < end_of_day else chunk_end + timedelta(seconds=1)
        return events

    filters = payload.get("filters", {}) or {}

    def _item_from_event(e):
        return (
            e.get('ReportName')
            or e.get('DatasetName')
            or e.get('ArtifactName')
            or e.get('ObjectDisplayName')
            or e.get('ItemName')
            or ''
        )

    def _matches_filters(event, flt):
        if not flt:
            return True
        op = event.get('Activity') or event.get('OperationName') or ''
        ws = event.get('WorkSpaceName') or event.get('WorkspaceName') or ''
        user = event.get('UserId') or event.get('UserName') or ''
        dom = event.get('domain') or ''
        app = _clean_app_name(event)
        status = flt.get('status', '')
        if flt.get('type'):
            if op not in flt['type']:
                return False
        if flt.get('dom'):
            if dom not in flt['dom']:
                return False
        if flt.get('ws'):
            if ws not in flt['ws']:
                return False
        if flt.get('item'):
            if _item_from_event(event) not in flt['item']:
                return False
        if flt.get('user'):
            if user not in flt['user']:
                return False
        if flt.get('app'):
            if app not in flt['app']:
                return False
        if status == 'ok' and not _is_success(event):
            return False
        if status == 'fail' and _is_success(event):
            return False
        return True


    warning = None
    try:
        load_start, load_end = _snap_activity_window_utc(request_start, request_end)
        all_events = _load_activity_range(load_start, load_end, token)
    except Exception:
        if (request_end - request_start) >= timedelta(hours=720):
            load_start, load_end = _snap_activity_window_utc(
                request_end - timedelta(hours=360), request_end
            )
            all_events = _load_activity_range(load_start, load_end, token)
        elif (request_end - request_start) >= timedelta(hours=360):
            load_start, load_end = _snap_activity_window_utc(
                request_end - timedelta(hours=168), request_end
            )
            all_events = _load_activity_range(load_start, load_end, token)
        else:
            raise

    all_events = [e for e in all_events if _event_in_requested_range(e, request_start, request_end)]

    from api.domains import get_domain_for_workspace
    for e in all_events:
        ws_id = e.get("WorkspaceId")
        ws_name = e.get("WorkSpaceName") or e.get("WorkspaceName")
        e["domain"] = get_domain_for_workspace(workspace_id=ws_id, workspace_name=ws_name)

    if filters:
        all_events = [e for e in all_events if _matches_filters(e, filters)]

    original_count = len(all_events)
    print(f"  Activity API: {original_count} events loaded")

    filter_options = {
        "type": sorted({
            e.get('Activity') or e.get('OperationName') or '' for e in all_events if e.get('Activity') or e.get('OperationName')
        }),
        "ws": sorted({
            e.get('WorkSpaceName') or e.get('WorkspaceName') or '' for e in all_events if e.get('WorkSpaceName') or e.get('WorkspaceName')
        }),
        "domain": sorted({
            e.get("domain") for e in all_events if e.get("domain")
        }),
        "user": sorted({
            e.get('UserId') or e.get('UserName') or '' for e in all_events if e.get('UserId') or e.get('UserName')
        }),
        "app": sorted({
            _clean_app_name(e) for e in all_events if _clean_app_name(e)
        }),
        "item": sorted({
            _item_from_event(e) for e in all_events if _item_from_event(e)
        }),
    }




    summary_totals = {
        "totalEvents": original_count,
        "uniqueUsers": len({
            e.get('UserId') or e.get('UserName') or '' for e in all_events if e.get('UserId') or e.get('UserName')
        }),
        "viewReportCount": sum(1 for e in all_events if (e.get('Activity') or e.get('OperationName')) == 'ViewReport'),
        "refreshCount": sum(1 for e in all_events if (e.get('Activity') or e.get('OperationName')) == 'RefreshDataset'),
        "externalCount": sum(1 for e in all_events if (e.get('Activity') or e.get('OperationName')) == 'ConnectFromExternalApplication'),
        "failureCount": sum(1 for e in all_events if not _is_success(e)),
    }

    chart_aggregates = _compute_chart_aggregates(all_events)

    MAX_EVENTS = 10000
    if filters:
        returned_events = all_events
        truncated = False
    else:
        returned_events = all_events
        truncated = False
        if len(all_events) > MAX_EVENTS:
            returned_events = all_events[-MAX_EVENTS:]
            truncated = True
            warning = (warning + ' ' if warning else '') + (
                f"Dataset too large; only the last {MAX_EVENTS} rows are listed below. "
                f"Charts and rankings use the full {original_count:,} events.")

    result = {
        "activityEventEntities": returned_events,
        "originalCount": original_count,
        "filteredCount": original_count,
        "truncated": truncated,
        "filterOptions": filter_options,
        "summaryTotals": summary_totals,
        "chartAggregates": chart_aggregates,
    }
    if warning:
        result["warning"] = warning
    return result

import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from auth import get_token, call_api

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_BASE_DIR, '.cache', 'activityevents')
os.makedirs(_CACHE_DIR, exist_ok=True)


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


def handle_activity(payload):
    token = get_token()

    start_str = payload.get("start")
    end_str   = payload.get("end")

    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc) - timedelta(hours=1)
    end_dt   = datetime.fromisoformat(end_str.replace("Z",   "+00:00")) if end_str   else datetime.now(timezone.utc)

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

    def _matches_filters(event, flt):
        if not flt:
            return True
        op = event.get('Activity') or event.get('OperationName') or ''
        ws = event.get('WorkSpaceName') or event.get('WorkspaceName') or ''
        user = event.get('UserId') or event.get('UserName') or ''
        status = flt.get('status', '')
        if flt.get('type'):
            if op not in flt['type']:
                return False
        if flt.get('ws'):
            if ws not in flt['ws']:
                return False
        if flt.get('user'):
            if user not in flt['user']:
                return False
        if status == 'ok' and event.get('IsSuccess') is False:
            return False
        if status == 'fail' and event.get('IsSuccess') is not False:
            return False
        return True

    original_start = start_dt
    original_end = end_dt
    warning = None
    try:
        all_events = _load_activity_range(start_dt, end_dt, token)
    except Exception as exc:
        if (original_end - original_start) >= timedelta(hours=720):
            start_dt = original_end - timedelta(hours=360)
            all_events = _load_activity_range(start_dt, original_end, token)
        elif (original_end - original_start) >= timedelta(hours=360):
            start_dt = original_end - timedelta(hours=168)
            all_events = _load_activity_range(start_dt, original_end, token)
        else:
            raise

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
        "user": sorted({
            e.get('UserId') or e.get('UserName') or '' for e in all_events if e.get('UserId') or e.get('UserName')
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
        "failureCount": sum(1 for e in all_events if e.get('IsSuccess') is False),
    }

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
                f"Dataset too large; only the last {MAX_EVENTS} events were returned to the browser.")

    result = {
        "activityEventEntities": returned_events,
        "originalCount": original_count,
        "filteredCount": original_count,
        "truncated": truncated,
        "filterOptions": filter_options,
        "summaryTotals": summary_totals,
    }
    if warning:
        result["warning"] = warning
    return result

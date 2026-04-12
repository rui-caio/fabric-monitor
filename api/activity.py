from datetime import datetime, timezone, timedelta

from auth import get_token, call_api


def handle_activity(payload):
    token = get_token()

    start_str = payload.get("start")
    end_str   = payload.get("end")

    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc) - timedelta(hours=1)
    end_dt   = datetime.fromisoformat(end_str.replace("Z",   "+00:00")) if end_str   else datetime.now(timezone.utc)

    fmt = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    all_events = []
    cursor = start_dt

    while cursor < end_dt:
        end_of_day = cursor.replace(hour=23, minute=59, second=59, microsecond=0)
        chunk_end  = min(end_dt, cursor + timedelta(hours=1), end_of_day)

        s = fmt(cursor)
        e = fmt(chunk_end)
        url = (f"https://api.powerbi.com/v1.0/myorg/admin/activityevents"
               f"?startDateTime=%27{s}%27&endDateTime=%27{e}%27")

        print(f"  Chunk: {s} → {e}")

        while url:
            status, data = call_api(url, token)
            if status != 200:
                err = data.get("error", data.get("message", str(data)))
                raise Exception(f"Activity API erro {status}: {err}")
            events = data.get("activityEventEntities", [])
            all_events.extend(events)
            url = data.get("continuationUri") or data.get("@odata.nextLink")

        cursor = chunk_end if chunk_end < end_of_day else chunk_end + timedelta(seconds=1)

    print(f"  Activity API: {len(all_events)} eventos carregados")
    return {"activityEventEntities": all_events}

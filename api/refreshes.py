from auth import get_token, call_api
from config import CAPACITY_ID


def handle_refreshes(payload):
    token    = get_token()
    top      = int(payload.get("top", 5000))
    url      = (f"https://api.powerbi.com/v1.0/myorg/admin/capacities/{CAPACITY_ID}/refreshables"
                f"?$top={top}")
    all_rows = []
    while url:
        status, data = call_api(url, token)
        if status != 200:
            raise Exception(f"Refreshables API erro {status}: {data.get('error','')}")
        rows = data.get("value", [])
        for r in rows:
            sched = r.get("refreshSchedule") or {}
            lr    = r.get("lastRefresh")     or {}
            avg   = r.get("averageDuration")
            med   = r.get("medianDuration")
            rpd   = r.get("refreshesPerDay") or 0
            try:    avg_f = float(str(avg).replace(",",".")) if avg not in (None,"") else None
            except: avg_f = None
            try:    med_f = float(str(med).replace(",",".")) if med not in (None,"") else None
            except: med_f = None
            daily_load = round(avg_f * rpd, 2) if avg_f is not None and rpd else None
            all_rows.append({
                "id":            r.get("id",""),
                "name":          r.get("name",""),
                "kind":          r.get("kind",""),
                "refresh_count": r.get("refreshCount") or 0,
                "refresh_failures": r.get("refreshFailures") or 0,
                "refreshes_per_day": rpd,
                "average_duration":  avg_f,
                "median_duration":   med_f,
                "daily_load_min":    daily_load,
                "configured_by":     ", ".join(x for x in (r.get("configuredBy") or []) if x),
                "schedule_enabled":  sched.get("enabled", False),
                "schedule_days":     ", ".join(x for x in (sched.get("days") or []) if x),
                "schedule_times":    ", ".join(x for x in (sched.get("times") or []) if x),
                "schedule_timezone": sched.get("localTimeZoneId",""),
                "last_status":       lr.get("status",""),
                "last_start":        lr.get("startTime",""),
                "last_end":          lr.get("endTime",""),
                "last_type":         lr.get("refreshType",""),
                "last_error":        "",
            })
        url = data.get("@odata.nextLink")

    datasets = [r for r in all_rows if r["kind"] == "Dataset"]
    print(f"  Refreshables: {len(datasets)} datasets carregados")
    return {"datasets": datasets}

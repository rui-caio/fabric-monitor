import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from auth import get_token
from config import CAPACITY_ID, METRICS_WS, METRICS_DS


def handle_capacity(payload):
    token = get_token()
    hours = int(payload.get("hours", 1))

    now  = datetime.now(timezone.utc)
    frm  = now - timedelta(hours=hours)

    sy, sm, sd = frm.year, frm.month, frm.day
    ey, em, ed = (now + timedelta(days=1)).year, (now + timedelta(days=1)).month, (now + timedelta(days=1)).day

    dax = """EVALUATE SUMMARIZECOLUMNS(
    'Timepoints'[Timepoint],
    TREATAS({"CAP_ID_PLACEHOLDER"}, 'Capacities'[Capacity Id]),
    FILTER(
        KEEPFILTERS(VALUES('Dates'[Date])),
        'Dates'[Date] >= DATE(SY, SM, SD) && 'Dates'[Date] <= DATE(EY, EM, ED)
    ),
    "Interactive",    'All Measures'[Interactive billable CU %],
    "Background",     'All Measures'[Background billable CU %],
    "Interactive_nb", 'All Measures'[Interactive non billable CU %],
    "Background_nb",  'All Measures'[Background non billable CU %],
    "SKU_CU",         'All Measures'[SKU CU by timepoint %],
    "CU_limit",       'All Measures'[CU limit]
)
ORDER BY 'Timepoints'[Timepoint] ASC"""

    dax = (dax
        .replace("CAP_ID_PLACEHOLDER", CAPACITY_ID)
        .replace("SY", str(sy)).replace("SM", str(sm)).replace("SD", str(sd))
        .replace("EY", str(ey)).replace("EM", str(em)).replace("ED", str(ed))
    )

    url  = f"https://api.powerbi.com/v1.0/myorg/groups/{METRICS_WS}/datasets/{METRICS_DS}/executeQueries"
    body = json.dumps({
        "queries": [{"query": dax}],
        "serializerSettings": {"includeNulls": True}
    }).encode()

    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        if e.code == 404 and "PowerBIFolderNotFound" in err:
            err = (
                f"{err}\n  → Check METRICS_WS in .env: must be the Power BI *workspace* (group) id "
                f"that contains the capacity metrics dataset (not the capacity id). "
                f"Service principals need access to that workspace."
            )
        raise Exception(f"Capacity API erro {e.code}: {err}")

    rows = []
    try:
        raw_rows = data["results"][0]["tables"][0]["rows"]
        frm_str = frm.strftime("%Y-%m-%dT%H:%M:%S")
        for row in raw_rows:
            tp = row.get("Timepoints[Timepoint]", "")
            if tp >= frm_str:
                rows.append({
                    "timepoint":       tp,
                    "interactive":     row.get("[Interactive]", 0) or 0,
                    "background":      row.get("[Background]", 0) or 0,
                    "interactive_nb":  row.get("[Interactive_nb]", 0) or 0,
                    "background_nb":   row.get("[Background_nb]", 0) or 0,
                    "sku_cu":          row.get("[SKU_CU]", 0) or 0,
                    "cu_limit":        row.get("[CU_limit]", 0) or 0,
                })
    except (KeyError, IndexError) as ex:
        raise Exception(f"Error processing response: {ex} | {str(data)[:300]}")

    print(f"  Capacity: {len(rows)} timepoints loaded")
    return {"timepoints": rows}

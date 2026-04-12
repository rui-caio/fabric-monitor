import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from auth import get_token
from config import CAPACITY_ID, METRICS_WS, METRICS_DS

_DAX_BACKGROUND = """DEFINE
	MPARAMETER 'TimePoint' = (DATE(TP_Y, TP_MO, TP_D) + TIME(TP_H, TP_MI, TP_S))
	MPARAMETER 'CapacitiesList' = {"CAP_ID"}
	VAR __DS0FilterTable = TREATAS(
		{"'Timepoint Background Detail'[Billing type]","'Timepoint Background Detail'[Start]","'Timepoint Background Detail'[End]"},
		'Timepoint detail page optional columns (background operations)'[DynamicColumnsTimepointBackgroundOperations Fields]
	)
	VAR __DS0FilterTable2 = TREATAS({(DATE(TP_Y, TP_MO, TP_D) + TIME(TP_H, TP_MI, TP_S))}, 'Timepoints'[Timepoint])
	VAR __DS0FilterTable3 = TREATAS({"CAP_ID"}, 'Capacities'[Capacity Id])
	VAR __DS0FilterTable4 = FILTER(KEEPFILTERS(VALUES('Dates'[Date])),
		AND(AND(AND('Dates'[Date] >= DATE(FD_Y,FD_M,FD_D), 'Dates'[Date] < DATE(TD_Y,TD_M,TD_D)),
		'Dates'[Date] >= DATE(2026, 4, 1)), 'Dates'[Date] < DATE(TD_Y,TD_M,TD_D)))
	VAR __DS0Core = SUMMARIZECOLUMNS(
		ROLLUPADDISSUBTOTAL(ROLLUPGROUP(
			'Timepoint Background Detail'[Operation start time],
			'Timepoint Background Detail'[Operation end time],
			'Timepoint Background Detail'[Status],
			'Timepoint Background Detail'[Operation],
			'Timepoint Background Detail'[User],
			'Items'[Workspace name],
			'Items'[Item kind],
			'Items'[Unique key],
			'Timepoint Background Detail'[Billing type],
			'Timepoint Background Detail'[Start],
			'Timepoint Background Detail'[End],
			'Items'[Item name]
		), "IsGrandTotalRowTotal"),
		__DS0FilterTable, __DS0FilterTable2, __DS0FilterTable3, __DS0FilterTable4,
		"SumTotal_CU__s_",        CALCULATE(SUM('Timepoint Background Detail'[Total CU (s)])),
		"SumDuration__s_",        CALCULATE(SUM('Timepoint Background Detail'[Duration (s)])),
		"SumTimepoint_CU__s_",    CALCULATE(SUM('Timepoint Background Detail'[Timepoint CU (s)])),
		"SumThrottling__s_",      CALCULATE(SUM('Timepoint Background Detail'[Throttling (s)])),
		"Sumv__of_base_capacity", CALCULATE(SUM('Timepoint Background Detail'[% of base capacity]))
	)
	VAR __DS0PrimaryWindowed = TOPN(502, __DS0Core, [IsGrandTotalRowTotal], 0, [SumTotal_CU__s_], 0,
		'Timepoint Background Detail'[Operation start time], 1,
		'Timepoint Background Detail'[Operation end time], 1,
		'Timepoint Background Detail'[Status], 1,
		'Timepoint Background Detail'[Operation], 1,
		'Timepoint Background Detail'[User], 1,
		'Items'[Workspace name], 1,
		'Items'[Item kind], 1,
		'Items'[Item name], 1,
		'Items'[Unique key], 1,
		'Timepoint Background Detail'[Billing type], 1,
		'Timepoint Background Detail'[Start], 1,
		'Timepoint Background Detail'[End], 1
	)
EVALUATE __DS0PrimaryWindowed
ORDER BY [IsGrandTotalRowTotal] DESC, [SumTotal_CU__s_] DESC,
	'Timepoint Background Detail'[Operation start time],
	'Timepoint Background Detail'[Operation], 'Timepoint Background Detail'[User],
	'Items'[Workspace name], 'Items'[Item name]"""

_DAX_INTERACTIVE = """DEFINE
	MPARAMETER 'TimePoint' = (DATE(TP_Y, TP_MO, TP_D) + TIME(TP_H, TP_MI, TP_S))
	MPARAMETER 'CapacitiesList' = {"CAP_ID"}
	VAR __DS0FilterTable = TREATAS(
		{"'Timepoint Interactive Detail'[Billing type]"},
		'Timepoint detail page optional columns (interactive operations)'[Interactive Operation optional columns  Fields]
	)
	VAR __DS0FilterTable2 = TREATAS({(DATE(TP_Y, TP_MO, TP_D) + TIME(TP_H, TP_MI, TP_S))}, 'Timepoints'[Timepoint])
	VAR __DS0FilterTable3 = TREATAS({"CAP_ID"}, 'Capacities'[Capacity Id])
	VAR __DS0FilterTable4 = FILTER(KEEPFILTERS(VALUES('Dates'[Date])),
		AND(AND(AND('Dates'[Date] >= DATE(FD_Y,FD_M,FD_D), 'Dates'[Date] < DATE(TD_Y,TD_M,TD_D)),
		'Dates'[Date] >= DATE(2026, 4, 1)), 'Dates'[Date] < DATE(TD_Y,TD_M,TD_D)))
	VAR __DS0Core = SUMMARIZECOLUMNS(
		ROLLUPADDISSUBTOTAL(ROLLUPGROUP(
			'Timepoint Interactive Detail'[Operation start time],
			'Timepoint Interactive Detail'[Operation end time],
			'Timepoint Interactive Detail'[Status],
			'Timepoint Interactive Detail'[Operation],
			'Timepoint Interactive Detail'[User],
			'Items'[Workspace name],
			'Items'[Item kind],
			'Items'[Unique key],
			'Timepoint Interactive Detail'[Billing type],
			'Items'[Item name]
		), "IsGrandTotalRowTotal"),
		__DS0FilterTable, __DS0FilterTable2, __DS0FilterTable3, __DS0FilterTable4,
		"Sumv__of_base_capacity", CALCULATE(SUM('Timepoint Interactive Detail'[% of base capacity])),
		"SumThrottling__s_",      CALCULATE(SUM('Timepoint Interactive Detail'[Throttling (s)])),
		"SumDuration__s_",        CALCULATE(SUM('Timepoint Interactive Detail'[Duration (s)])),
		"SumTimepoint_CU__s_",    CALCULATE(SUM('Timepoint Interactive Detail'[Timepoint CU (s)])),
		"SumTotal_CU__s_",        CALCULATE(SUM('Timepoint Interactive Detail'[Total CU (s)]))
	)
	VAR __DS0PrimaryWindowed = TOPN(502, __DS0Core, [IsGrandTotalRowTotal], 0, [Sumv__of_base_capacity], 0,
		'Timepoint Interactive Detail'[Billing type], 1,
		'Timepoint Interactive Detail'[Operation start time], 1,
		'Timepoint Interactive Detail'[Operation end time], 1,
		'Timepoint Interactive Detail'[Status], 1,
		'Timepoint Interactive Detail'[Operation], 1,
		'Timepoint Interactive Detail'[User], 1,
		'Items'[Workspace name], 1,
		'Items'[Item kind], 1,
		'Items'[Item name], 1,
		'Items'[Unique key], 1
	)
EVALUATE __DS0PrimaryWindowed
ORDER BY [IsGrandTotalRowTotal] DESC, [Sumv__of_base_capacity] DESC,
	'Timepoint Interactive Detail'[Billing type],
	'Timepoint Interactive Detail'[Operation start time],
	'Timepoint Interactive Detail'[Operation], 'Timepoint Interactive Detail'[User],
	'Items'[Workspace name], 'Items'[Item name]"""


def handle_timepoint(payload):
    """Drill-down detail for a specific timepoint — Interactive and Background."""
    token = get_token()
    tp    = payload.get("timepoint", "")
    mode  = payload.get("mode", "interactive")

    if not tp:
        raise Exception("timepoint em falta")

    try:
        dt = datetime.fromisoformat(tp)
    except ValueError:
        raise Exception(f"Formato de timepoint inválido: {tp}")

    y, mo, d  = dt.year, dt.month, dt.day
    h, mi, s  = dt.hour, dt.minute, dt.second

    fd   = dt.date()
    fd_y, fd_m, fd_d = fd.year, fd.month, fd.day
    td   = (dt + timedelta(days=1)).date()
    td_y, td_m, td_d = td.year, td.month, td.day

    dax = _DAX_BACKGROUND if mode == "background" else _DAX_INTERACTIVE
    dax = (dax
        .replace("TP_Y",  str(y)).replace("TP_MO", str(mo)).replace("TP_D",  str(d))
        .replace("TP_H",  str(h)).replace("TP_MI", str(mi)).replace("TP_S",  str(s))
        .replace("FD_Y",  str(fd_y)).replace("FD_M", str(fd_m)).replace("FD_D", str(fd_d))
        .replace("TD_Y",  str(td_y)).replace("TD_M", str(td_m)).replace("TD_D", str(td_d))
        .replace("CAP_ID", CAPACITY_ID)
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
        raise Exception(f"Timepoint API erro {e.code}: {e.read().decode(errors='replace')}")

    rows = []
    try:
        raw = data["results"][0]["tables"][0]["rows"]
        for row in raw:
            if row.get("[IsGrandTotalRowTotal]", False):
                continue
            if mode == "background":
                rows.append({
                    "operation":    row.get("Timepoint Background Detail[Operation]", ""),
                    "user":         row.get("Timepoint Background Detail[User]", ""),
                    "workspace":    row.get("Items[Workspace name]", ""),
                    "item":         row.get("Items[Item name]", ""),
                    "item_kind":    row.get("Items[Item kind]", ""),
                    "status":       row.get("Timepoint Background Detail[Status]", ""),
                    "billing_type": row.get("Timepoint Background Detail[Billing type]", ""),
                    "start":        row.get("Timepoint Background Detail[Operation start time]", ""),
                    "end":          row.get("Timepoint Background Detail[Operation end time]", ""),
                    "total_cu":     row.get("[SumTotal_CU__s_]", 0) or 0,
                    "timepoint_cu": row.get("[SumTimepoint_CU__s_]", 0) or 0,
                    "duration":     row.get("[SumDuration__s_]", 0) or 0,
                    "throttling":   row.get("[SumThrottling__s_]", 0) or 0,
                    "pct_capacity": row.get("[Sumv__of_base_capacity]", 0) or 0,
                })
            else:
                rows.append({
                    "operation":    row.get("Timepoint Interactive Detail[Operation]", ""),
                    "user":         row.get("Timepoint Interactive Detail[User]", ""),
                    "workspace":    row.get("Items[Workspace name]", ""),
                    "item":         row.get("Items[Item name]", ""),
                    "item_kind":    row.get("Items[Item kind]", ""),
                    "status":       row.get("Timepoint Interactive Detail[Status]", ""),
                    "billing_type": row.get("Timepoint Interactive Detail[Billing type]", ""),
                    "start":        row.get("Timepoint Interactive Detail[Operation start time]", ""),
                    "end":          row.get("Timepoint Interactive Detail[Operation end time]", ""),
                    "total_cu":     row.get("[SumTotal_CU__s_]", 0) or 0,
                    "timepoint_cu": row.get("[SumTimepoint_CU__s_]", 0) or 0,
                    "duration":     row.get("[SumDuration__s_]", 0) or 0,
                    "throttling":   row.get("[SumThrottling__s_]", 0) or 0,
                    "pct_capacity": row.get("[Sumv__of_base_capacity]", 0) or 0,
                })
    except (KeyError, IndexError) as ex:
        raise Exception(f"Erro ao processar resposta: {ex}")

    print(f"  Timepoint {tp} [{mode}]: {len(rows)} operações")
    return {"rows": rows, "timepoint": tp, "mode": mode}

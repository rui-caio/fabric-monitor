import sys
import os
import json

sys.path.append(os.getcwd())
from auth import get_token, call_api
from config import SCOPES, METRICS_WS, METRICS_DS

def query_dax(query):
    token = get_token(SCOPES)
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{METRICS_WS}/datasets/{METRICS_DS}/executeQueries"
    
    import urllib.request
    req = urllib.request.Request(
        url,
        data=json.dumps({"queries": [{"query": query}]}).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode(errors='replace')}")
        return None

if __name__ == "__main__":
    q = "EVALUATE FILTER(INFO.COLUMNS(), [TableID] = \"Items\")"
    res = query_dax(q)
    if res and "results" in res:
        cols = [r["ExplicitName"] for r in res["results"][0]["tables"][0]["rows"]]
        print("Items columns:")
        for c in cols: print(f"  {c}")

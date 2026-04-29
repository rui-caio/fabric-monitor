import sys
import os
import json

sys.path.append(os.getcwd())
from auth import get_token, call_api
from config import SCOPES, CAPACITY_ID, METRICS_WS, METRICS_DS

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
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    # Query the DMVs for tables/columns containing 'domain'
    q = "EVALUATE FILTER(INFO.COLUMNS(), FIND(\"domain\", LOWER([ExplicitName]), 1, 0) > 0)"
    res = query_dax(q)
    print(json.dumps(res, indent=2))

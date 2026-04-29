import sys
import os
import json

sys.path.append(os.getcwd())
from auth import get_token, call_api
from config import SCOPES

def test_pbi_token_on_fabric():
    print("Getting PBI token...")
    token = get_token(SCOPES)
    if not token:
        print("Failed to get token.")
        return
        
    print("Token acquired. Calling Fabric Workspaces API...")
    url = "https://api.fabric.microsoft.com/v1/workspaces"
    status, data = call_api(url, token)
    
    print(f"Status: {status}")
    if status == 200:
        print("SUCCESS! Power BI token works on Fabric API.")
        workspaces = data.get("value", [])
        print(f"Found {len(workspaces)} workspaces.")
        if workspaces:
            print(f"Sample: {workspaces[0]}")
    else:
        print("FAILED.")
        print(data)

if __name__ == "__main__":
    test_pbi_token_on_fabric()

import msal

app = msal.PublicClientApplication(
    "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
    authority="https://login.microsoftonline.com/common"
)

scopes = [
    "https://analysis.windows.net/powerbi/api/.default",
    "https://api.fabric.microsoft.com/.default"
]

flow = app.initiate_device_flow(scopes=scopes)
if "user_code" in flow:
    print("SUCCESS! Flow initiated.")
    print(flow)
else:
    print("FAILED!")
    print(flow)

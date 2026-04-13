# Fabric Monitor

A local monitoring dashboard for **Microsoft Fabric** capacities — tracks compute unit consumption, user activity, and dataset refresh metrics in real time through a browser-based interface.

---

## Features

### Capacity Utilisation Tab

Visualises compute unit (CU) consumption over time by querying the **Microsoft Fabric Capacity Metrics** semantic model via DAX.

- **Interactive vs Background breakdown** — stacked area chart showing billable CU consumption split by operation type. Interactive operations are user-triggered (report loads, queries); background operations run autonomously (refreshes, scheduled flows)
- **SKU CU % chart** — total capacity utilisation as a percentage of the SKU ceiling, computed from all four components: interactive billable, background billable, interactive non-billable, and background non-billable CU
- **Four KPI cards** — average billable CU, average interactive CU, average background CU, and peak total utilisation over the selected period
- **Configurable time window** — load the last 1, 2, 4, 6, 12, 24, or 48 hours of data
- **Sortable detail table** — every timepoint listed with its Interactive %, Background %, and computed SKU CU %, colour-coded by severity thresholds
- **Timepoint drill-down panel** — click any bar on the chart to open a side panel with the full operation list for that 30-second timepoint:
  - Switch between **Interactive** and **Background** operation modes
  - **Group by** any combination of dimensions: Operation, User, Item, Workspace, Type, Status, Billing Type — metrics are aggregated across the active grouping
  - **Filter pills** for each dimension — multi-value dropdown filters applied locally without an extra API call
  - Metric summary cards showing total CU (s), Timepoint CU (s), Duration (s), and % Capacity for the current view
  - CU bar chart per row to visualise relative cost at a glance
  - Export to Excel with all active grouping dimensions and metrics

---

### Activity Log Tab

Reads Power BI user activity events from the **Power BI Activity Events Admin API**, with hourly chunking and local disk cache to avoid redundant API calls.

- **Six KPI cards** — total operations, unique users, reports viewed (ViewReport), refreshes triggered (RefreshDataset), external connections (ConnectFromExternalApplication), and failures (IsSuccess = false)
- **Operations per Hour chart** — stacked bar chart by hour with four series: View Report, Refresh, External, and Other — shows demand pattern over the selected period
- **Distribution by Hour of Day** — bar chart showing which hours of the day see the most activity, regardless of date, useful for identifying peak usage windows
- **Access Method chart** — breaks down how users connect: Power BI Desktop (MSOLAP), Excel, Azure Client, Web Browser, System/API, or Other — derived from UserAgent when ConsumptionMethod is absent
- **Artifact Type chart** — distribution of operations by ArtifactKind or ObjectType (Report, Dashboard, Dataset, Dataflow, etc.)
- **Operation Type chart** — top 12 operation types by frequency, covering the full range of Power BI activity event names
- **Rankings section** — top 15 leaderboards for: most-viewed reports, most-accessed datasets, most-active users, most-active workspaces, external applications (by AppName/UserAgent), and operations with the most failures
- **Multi-select filters** — filter by operation type, workspace, and user simultaneously; a status toggle filters for successful or failed events only. Filters are applied client-side on cached data; when the dataset is truncated the backend is re-queried with the active filter set to return full results
- **Sortable detail table** — up to 500 rows displayed, sortable by any column (Time, Operation, User, Item, Workspace, Method, IP, Status); includes operation-type colour badges
- **Configurable time window** — from the last hour up to the last 30 days; the cache stores data per hour-long chunk so re-loading a previously fetched range is instantaneous
- **Large dataset handling** — when the event count exceeds 10,000, only the most recent events are sent to the browser; a warning banner explains the truncation and filters trigger a fresh server-side query
- **Export to Excel** — exports all current activity rows with columns: Time, Operation, User, Item, Workspace, Method, IP, Status

---

### Refreshes Tab

Reads dataset refresh metadata from the **Power BI Capacity Refreshables Admin API**, including schedule configuration, historical statistics, and per-dataset performance.

- **Six KPI cards** — total datasets with refresh configured, active schedules, total refreshes executed in the period, total failures, total estimated daily load (minutes), and average refresh duration
- **Refreshes by Hour of Day chart** — distribution of scheduled refresh times across 24 hours, showing when the capacity is under most scheduled load
- **Last Refresh Status donut** — proportion of datasets with their last refresh in Completed, Failed, or Unknown state
- **Duration Distribution chart** — histogram of average refresh durations bucketed into six ranges (< 0.5 min, 0.5–1 min, 1–5 min, 5–15 min, 15–30 min, > 30 min)
- **Rankings section** — top 15 datasets by: daily load (avg duration × refreshes per day), total refreshes executed, total failures, and average duration; each with a proportional bar
- **Filters** — multi-select by owner (configured-by user) and dataset name; dropdowns for schedule status (Active / Inactive / No schedule) and last refresh status (Completed / Failed / Unknown)
- **Sortable detail table** — all datasets with columns: Workspace, Dataset, Configured By, Schedule status badge, Ref/Day (actual count from schedule times, not the capacity maximum), Times, Days, Avg Duration (min), Load/Day (min), Total Ref., Failures, Last Status, Last Refresh timestamp. Duration and load columns are colour-coded: amber above 5 min average, red above 30 min daily load
- **Export to Excel** — exports the full filtered dataset list with all columns

---

## Requirements

### System

| Requirement | Minimum version |
|-------------|----------------|
| Python | 3.8+ |
| pip | any recent version |

### Python library

```bash
pip install msal
```

All other dependencies (`json`, `urllib`, `http.server`, `threading`) are part of the Python standard library — no additional installations required.

### Browser

Any modern browser with ES6+ support (Chrome, Edge, Firefox, Safari).
Chart.js is loaded automatically via CDN — internet access is required on first load.

---

## Microsoft / Azure Prerequisites

### 1. Azure Active Directory (Entra ID)

- An account with **Power BI Admin** or **Fabric Admin** permissions in the tenant
- The **Tenant ID** of your Azure AD

> How to find it: [portal.azure.com](https://portal.azure.com) → Azure Active Directory → Overview → **Directory (tenant) ID**

### 2. Microsoft Fabric Capacity

- An active Fabric capacity (F-SKU or P-SKU)
- The **Capacity ID** of the capacity to monitor

> How to find it: [app.powerbi.com](https://app.powerbi.com) → Admin Portal → Capacity Settings → select the capacity → the ID appears in the URL or in the settings panel

### 3. Microsoft Fabric Capacity Metrics app

The capacity utilisation data is read through the official **Microsoft Fabric Capacity Metrics** app, which must be installed in your tenant.

You need two IDs from that app's dataset:

| Variable | What it is |
|----------|-----------|
| `METRICS_WS` | ID of the workspace where the Capacity Metrics app is installed |
| `METRICS_DS` | ID of the Capacity Metrics app's dataset |

> How to find them: open the Capacity Metrics app workspace in Power BI → click on the dataset → the URL has the format:
> `app.powerbi.com/groups/{METRICS_WS}/datasets/{METRICS_DS}`

### 4. Required permissions

The account used for authentication needs:

- `Tenant.Read.All` or `Tenant.ReadWrite.All` — for the Activity Log API
- **Viewer** access (or higher) to the Capacity Metrics workspace
- **Fabric Administrator** or **Power BI Administrator** role in the tenant — to access the Capacity and Refreshables APIs

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/rui-caio/fabric-monitor.git
cd fabric-monitor
```

### 2. Install dependencies

```bash
pip install msal
```

### 3. Configure the `.env` file

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
CAPACITY_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
METRICS_WS=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
METRICS_DS=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ORG_NAME=Your Org
PORT=8765
```

> **Important:** The `.env` file is listed in `.gitignore` and must never be committed or shared. It contains sensitive configuration values.

---

## Usage

### Start the server

```bash
python fabric_proxy.py
```

### Authentication (first run)

On the first run, the terminal displays a device code prompt:

```
────────────────────────────────────────────────────────────
  AUTHENTICATION REQUIRED
────────────────────────────────────────────────────────────

  1. Open: https://microsoft.com/devicelogin
  2. Code:  XXXX-XXXX

  Waiting...
```

1. Open your browser at `https://microsoft.com/devicelogin`
2. Enter the code shown in the terminal
3. Sign in with your Microsoft account with the required permissions
4. Return to the terminal — authentication completes automatically

The token is kept in memory for the duration of the session. On the next run, if the token is still valid, authentication is silent.

### Open the dashboard

Once authenticated, open your browser at:

```
http://localhost:8765
```

The dashboard is also accessible from other machines on the same local network at `http://<your-ip>:8765`. The server prints the local IP address on startup.

### Stop the server

```
Ctrl+C
```

---

## Project structure

```
fabric-monitor/
├── fabric_proxy.py        # Entry point — starts the HTTP server
├── config.py              # Loads .env and exposes configuration constants
├── auth.py                # MSAL authentication (Device Code Flow)
├── server.py              # HTTP request handler and main()
│
├── api/
│   ├── activity.py        # /api/activity — user activity events with disk cache
│   ├── capacity.py        # /api/capacity — CU consumption via DAX
│   ├── timepoint.py       # /api/timepoint — per-timepoint operation drill-down
│   └── refreshes.py       # /api/refreshes — dataset refresh metrics
│
├── static/
│   └── index.html         # Frontend (HTML + CSS + JavaScript + Chart.js)
│
├── .cache/
│   └── activityevents/    # Hourly activity event cache (auto-created)
│
├── .env                   # Local configuration (do NOT commit)
├── .env.example           # Configuration template
└── .gitignore
```

---

## Local API endpoints

The server exposes the following endpoints at `http://localhost:8765`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the frontend HTML |
| `POST` | `/api/ping` | Health check |
| `POST` | `/api/auth_status` | Current authentication state and account |
| `POST` | `/api/activity` | Activity events for a date range (with optional filters) |
| `POST` | `/api/capacity` | CU consumption for the last N hours |
| `POST` | `/api/timepoint` | Operation detail for a specific timepoint |
| `POST` | `/api/refreshes` | Dataset refresh metrics and schedules |

---

## Microsoft APIs used

| API | Purpose |
|-----|---------|
| [Power BI Activity Events API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-activity-events) | User activity log |
| [Power BI Capacity Refreshables API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-capacities-refreshables) | Dataset refresh metrics and schedules |
| [Power BI Execute Queries API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries-in-group) | DAX queries against the Capacity Metrics dataset |

Authentication uses [MSAL Device Code Flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/msal-authentication-flows#device-code) — no passwords or secrets are stored.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TENANT_ID` | Yes | Azure AD tenant ID |
| `CAPACITY_ID` | Yes | ID of the Fabric capacity to monitor |
| `METRICS_WS` | Yes | Workspace ID of the Capacity Metrics app |
| `METRICS_DS` | Yes | Dataset ID of the Capacity Metrics app |
| `ORG_NAME` | No | Organisation name shown in the dashboard title |
| `PORT` | No (default: `8765`) | Local server port |

---

## Troubleshooting

### `ERROR: missing configuration variables`
The `.env` file is missing or incomplete. Make sure you copied `.env.example` and filled in all required values.

### `ERROR: 'msal' library not found`
```bash
pip install msal
```

### Authentication fails or expires
The MSAL token is held in memory only. Restarting the server will prompt for authentication again. If the account lacks sufficient permissions, the device code flow completes but API calls return 403.

### `Activity API error 403`
The authenticated account does not have **Power BI Administrator** or **Fabric Administrator** role. Contact your tenant administrator.

### `Capacity API error 404` or empty data
Verify that `METRICS_WS` and `METRICS_DS` match the workspace and dataset of the **Microsoft Fabric Capacity Metrics** app in your tenant.

### Browser shows "Proxy not detected"
The Python server is not running or is using a different port. Confirm that `python fabric_proxy.py` is active in the terminal and that the `PORT` value in `.env` matches the URL you are accessing.

---

## Dependencies

| Dependency | Version | Source |
|------------|---------|--------|
| `msal` | any | `pip install msal` |
| `Chart.js` | 4.4.1 | CDN (loaded automatically) |
| `JetBrains Mono` | — | Google Fonts (loaded automatically) |
| `Syne` | — | Google Fonts (loaded automatically) |

---

## Security

- Configuration values (`TENANT_ID`, `CAPACITY_ID`, etc.) are read from environment variables / `.env` file and never hardcoded
- The `.env` file is excluded from git via `.gitignore`
- Microsoft authentication uses **Device Code Flow** — no passwords are stored anywhere
- The HTTP server binds to `0.0.0.0` but only serves data that is already accessible to the authenticated account; no data is stored permanently beyond the activity event cache

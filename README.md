# Curefoods Demand Planning Engine

An internal demand planning platform for Curefoods — automating demand forecasting, supply planning, recipe explosion, warehouse planning, and procurement recommendations across 50+ cloud kitchen outlets.

---

## Prerequisites

- **Python 3.11** (recommended via pyenv or direct install)
- **Docker Desktop** (for local ClickHouse)
- **Node.js 18+** (for the React frontend)
- **Git**

---

## Quick Start

### 1. Start Local ClickHouse (Docker)

```powershell
docker run -d --name clickhouse-local -p 8123:8123 -p 9000:9000 `
  -v clickhouse-data:/var/lib/clickhouse `
  -e CLICKHOUSE_PASSWORD=admin123 `
  -e CLICKHOUSE_USER=default `
  clickhouse/clickhouse-server
```

Verify it's running:
```powershell
docker ps
# Should show: clickhouse-local    Up X minutes
```

### 2. Set Up Python Environment

```powershell
# From d:\demand-planning\
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

> **Note on Prophet on Windows**: If Prophet install fails, run:
> ```powershell
> pip install pystan==3.9.0
> pip install prophet
> ```
> If it still fails, install Microsoft C++ Build Tools from:
> https://visualstudio.microsoft.com/visual-cpp-build-tools/

### 3. Configure Environment

```powershell
copy .env.example .env
# Edit .env and fill in your actual credentials
notepad .env
```

Required variables:
| Variable | Description |
|----------|-------------|
| `SOURCE_PASSWORD` | UrbanPiper ClickHouse password |
| `SUPPLYNOTE_EMAIL` | Your SupplyNote login email |
| `SUPPLYNOTE_PASSWORD` | Your SupplyNote login password |
| `SUPPLYNOTE_TOKEN` | Captured Bearer token from Chrome DevTools |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon key |

### 4. Create Database Tables

```powershell
python pipeline\create_tables.py
```

### 5. Run the Pipeline (with dummy data for first test)

```powershell
# Set USE_DUMMY_DATA=true in .env first for testing without live connections
python pipeline\main.py
```

### 6. Start the Backend API

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

### 7. Start the Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend available at: http://localhost:5173

---

## Project Structure

```
demand-planning/
├── .env                    # Your local environment variables (git-ignored)
├── .env.example            # Template — copy to .env and fill in
├── requirements.txt        # Python dependencies
├── README.md               # This file
│
├── pipeline/               # Data pipeline
│   ├── main.py             # Full pipeline orchestrator
│   ├── scheduler.py        # Cron-style job scheduler
│   ├── create_tables.py    # Creates all ClickHouse tables
│   ├── extractors/         # Data source connectors
│   ├── transformers/       # Data cleaning and UOM conversion
│   ├── loaders/            # ClickHouse insert layer
│   └── engines/            # 7 planning computation engines
│
├── backend/                # FastAPI REST API
│   ├── main.py             # App entry point
│   ├── database.py         # ClickHouse connection manager
│   ├── auth.py             # Supabase JWT verification
│   ├── models.py           # Pydantic response models
│   └── routers/            # 10 API route modules
│
├── frontend/               # React TypeScript app
│   ├── src/
│   │   ├── lib/            # Supabase + Axios clients
│   │   ├── hooks/          # useAuth, useRole
│   │   ├── components/     # Reusable UI components
│   │   └── pages/          # 11 application pages
│   └── package.json
│
└── logs/                   # Auto-created by pipeline
    ├── pipeline.log        # Main pipeline log
    └── raw/                # Raw JSON/CSV from sources
```

---

## User Roles

| Role | Pages |
|------|-------|
| `super_admin` | All pages |
| `planning_manager` | Dashboard, Sales, Forecast, Supply, Warehouse, Procurement, Alerts, Reports |
| `demand_planner` | Dashboard, Sales, Forecast, Supply, Alerts, Reports |
| `procurement` | Dashboard, Warehouse, Procurement, Alerts |
| `kitchen_ops` | Dashboard, Supply, Warehouse |
| `culinary_team` | Dashboard, Recipes |
| `leadership` | Dashboard, Reports |

---

## Data Sources

### UrbanPiper ClickHouse (orders & menu data)
- Pulls every night at 2 AM
- Last 90 days of orders and order items
- Full menu and recipe tables daily

### SupplyNote (inventory & procurement)
- Kitchen stock: every 4 hours
- Warehouse stock: every 4 hours
- Open POs: every 2 hours
- GRN log: every hour
- Vendor master: weekly

---

## Troubleshooting

**ClickHouse connection refused**
```powershell
docker ps  # Check if container is running
docker start clickhouse-local  # Start if stopped
```

**UrbanPiper connection blocked (office WiFi)**
- Switch to mobile hotspot
- Connection will auto-detect and suggest this

**Prophet install fails on Windows**
- Install C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
- Or use `conda install -c conda-forge prophet`

**SupplyNote token expired**
- The extractor auto-refreshes using `SUPPLYNOTE_EMAIL` and `SUPPLYNOTE_PASSWORD`
- Or manually capture a new token from Chrome DevTools and update `SUPPLYNOTE_TOKEN` in `.env`

---

## Running in Demo Mode

To run the entire stack without any external connections (for presentations or development):

```powershell
# In .env:
USE_DUMMY_DATA=true
DEMO_MODE=true

python pipeline\main.py         # Loads realistic dummy data
uvicorn backend.main:app --reload
cd frontend && npm run dev
```

---

## Deployment (GCP — Phase 2)

- Backend: GCP Cloud Run
- Frontend: Firebase Hosting
- Secrets: GCP Secret Manager
- Database: Keep local ClickHouse or migrate to ClickHouse Cloud

"""
backend/main.py
─────────────────
FastAPI application entry point.

Start with:
  uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

API docs at: http://localhost:8000/docs
"""

import os
import sys
import logging
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.routers import (
    dashboard,
    sales,
    forecast,
    supply,
    recipes,
    warehouse,
    procurement,
    alerts,
    reports,
    admin,
    tracker,
)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
)
log = logging.getLogger("backend.main")

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

app = FastAPI(
    title="Curefoods Demand Planning Engine",
    description="Internal demand forecasting and supply planning platform for Curefoods.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow Next.js dev server ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(dashboard.router,   prefix="/api", tags=["Dashboard"])
app.include_router(sales.router,       prefix="/api", tags=["Sales"])
app.include_router(forecast.router,    prefix="/api", tags=["Forecast"])
app.include_router(supply.router,      prefix="/api", tags=["Supply"])
app.include_router(recipes.router,     prefix="/api", tags=["Recipes"])
app.include_router(warehouse.router,   prefix="/api", tags=["Warehouse"])
app.include_router(procurement.router, prefix="/api", tags=["Procurement"])
app.include_router(alerts.router,      prefix="/api", tags=["Alerts"])
app.include_router(reports.router,     prefix="/api", tags=["Reports"])
app.include_router(tracker.router,     prefix="/api", tags=["Tracker"])
app.include_router(admin.router,       prefix="/api", tags=["Admin"])


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    from backend.database import get_client
    db_ok = False
    try:
        client = get_client()
        client.query("SELECT 1")
        client.close()
        db_ok = True
    except Exception:
        pass

    return {
        "status":    "ok" if db_ok else "degraded",
        "demo_mode": DEMO_MODE,
        "database":  "connected" if db_ok else "unavailable",
        "version":   "1.0.0",
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Curefoods Demand Planning Engine API",
        "docs":    "/docs",
        "health":  "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)



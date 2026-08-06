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
    variance,
)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
)
log = logging.getLogger("backend.main")

# Interactive API docs (/docs, /redoc, /openapi.json) expose the entire API
# surface -- every endpoint, parameter, and response shape -- to anyone who
# finds the URL, with no auth required to view them. Off by default;
# set ENABLE_API_DOCS=true (Render env var, or locally in .env) when someone
# genuinely needs to browse them -- e.g. onboarding a new developer, or
# debugging integration issues. Turn it back off afterward. Locally without
# this var set, docs are still reachable at localhost, which nobody outside
# your machine can hit anyway, so there's no need to set it for normal dev.
_docs_enabled = os.getenv("ENABLE_API_DOCS", "false").lower() == "true"

app = FastAPI(
    title="Curefoods Demand Planning Engine",
    description="Internal demand forecasting and supply planning platform for Curefoods.",
    version="1.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Only the real frontend origins get to call this API from a browser.
# Add a comma-separated ALLOWED_ORIGINS env var (Render/​.env) if another
# origin genuinely needs access (e.g. a Vercel preview deployment URL) --
# don't widen this back to "*" as a shortcut.
_default_origins = "https://cfi-demand-planning.vercel.app,http://localhost:3000"
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
app.include_router(variance.router,    prefix="/api", tags=["Variance"])


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    from backend.database import get_db
    db_ok = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    return {
        "status":    "ok" if db_ok else "degraded",
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




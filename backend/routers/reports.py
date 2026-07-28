"""backend/routers/reports.py — GET /api/reports/*"""

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import require_role, UserContext
from backend.database import query_df

router = APIRouter()


@router.get("/reports/accuracy")
def get_accuracy_report(
    days: int = Query(default=90),
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "leadership")),
):
    cache_df = query_df("SELECT payload FROM app_cache WHERE endpoint = 'reports_accuracy'")
    return cache_df["payload"].iloc[0] if not cache_df.empty else []


@router.get("/reports/stockouts")
def get_stockout_report(
    days: int = Query(default=90),
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "leadership")),
):
    cache_df = query_df("SELECT payload FROM app_cache WHERE endpoint = 'reports_stockouts'")
    return cache_df["payload"].iloc[0] if not cache_df.empty else []


@router.get("/reports/wastage")
def get_wastage_report(
    days: int = Query(default=30),
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "leadership")),
):
    cache_df = query_df("SELECT payload FROM app_cache WHERE endpoint = 'reports_wastage'")
    return cache_df["payload"].iloc[0] if not cache_df.empty else []


@router.get("/reports/vendor")
def get_vendor_performance(
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "leadership")),
):
    cache_df = query_df("SELECT payload FROM app_cache WHERE endpoint = 'reports_vendor'")
    return cache_df["payload"].iloc[0] if not cache_df.empty else []

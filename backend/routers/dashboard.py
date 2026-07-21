"""backend/routers/dashboard.py — GET /api/dashboard/summary"""

from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends
import pandas as pd

from backend.auth     import get_current_user, UserContext
from backend.database import query_df

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


import asyncio

@router.get("/dashboard/summary")
async def get_dashboard_summary(user: UserContext = Depends(get_current_user)):
    # 1. Run all three independent DB queries concurrently in thread pools
    cache_task = asyncio.to_thread(query_df, "SELECT payload FROM app_cache WHERE endpoint = 'dashboard_summary'")
    alerts_task = asyncio.to_thread(query_df, "SELECT severity, COUNT(*) AS cnt FROM alerts WHERE resolved = 0 GROUP BY severity")
    recent_task = asyncio.to_thread(query_df, 
        "SELECT alert_id, alert_type, severity, message, sku, outlet, ingredient, created_at, resolved "
        "FROM alerts ORDER BY created_at DESC LIMIT 10"
    )

    cache_df, alerts_df, recent_df = await asyncio.gather(cache_task, alerts_task, recent_task)

    # 2. Extract cache payload
    if cache_df.empty:
        # Fallback empty payload if pipeline hasn't run yet
        payload = {
            "total_orders_today": 0, "skus_at_risk": 0, "revenue_at_risk": 0.0,
            "forecast_accuracy_percent": 0.0, "last_data_refresh": None,
            "total_open_pos": 0, "overdue_pos": 0, "top_movers": [],
            "warehouse_sufficiency_pct": 100.0, "vendor_performance": []
        }
    else:
        payload = cache_df["payload"].iloc[0]

    # 3. Extract Real-Time Alerts
    active_alerts    = int(alerts_df["cnt"].sum()) if not alerts_df.empty else 0
    critical_alerts  = int(alerts_df[alerts_df["severity"] == "CRITICAL"]["cnt"].sum()) if not alerts_df.empty else 0

    recent_alerts = recent_df.to_dict(orient="records") if not recent_df.empty else []

    # 3. Merge live alerts into cached payload
    payload["active_alerts_count"] = active_alerts
    payload["critical_alerts_count"] = critical_alerts
    payload["recent_alerts"] = recent_alerts

    return payload

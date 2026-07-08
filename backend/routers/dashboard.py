"""backend/routers/dashboard.py — GET /api/dashboard/summary"""

from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends
import pandas as pd

from backend.auth     import get_current_user, UserContext
from backend.database import query_df

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/dashboard/summary")
async def get_dashboard_summary(user: UserContext = Depends(get_current_user)):
    today = date.today()

    # Today's orders
    orders_df = query_df(f"SELECT count() AS cnt FROM fact_orders_raw WHERE toDate(created_at) = '{today}'")
    total_orders_today = int(orders_df["cnt"].iloc[0]) if not orders_df.empty else 0

    # Alerts counts
    alerts_df = query_df("SELECT severity, count() AS cnt FROM alerts WHERE resolved = 0 GROUP BY severity")
    active_alerts    = int(alerts_df["cnt"].sum()) if not alerts_df.empty else 0
    critical_alerts  = int(alerts_df[alerts_df["severity"] == "CRITICAL"]["cnt"].sum()) if not alerts_df.empty else 0

    # SKUs at risk
    risk_df = query_df(
        f"SELECT count(DISTINCT sku) AS cnt FROM fact_forecast "
        f"WHERE forecast_date = '{today}' AND qty_predicted > 0"
    )
    skus_at_risk = int(risk_df["cnt"].iloc[0]) if not risk_df.empty else 0

    # Forecast accuracy (avg from last pipeline run context — simplified)
    accuracy = 78.5  # placeholder until real MAPE stored per run

    # Last data refresh
    refresh_df = query_df(
        "SELECT max(completed_at) AS last FROM pipeline_runs WHERE status = 'SUCCESS'"
    )
    last_refresh = None
    if not refresh_df.empty and refresh_df["last"].iloc[0] is not None:
        last_refresh = pd.to_datetime(refresh_df["last"].iloc[0]).isoformat()

    # Recent alerts
    recent_df = query_df(
        "SELECT alert_id, alert_type, severity, message, sku, outlet, ingredient, created_at, resolved "
        "FROM alerts ORDER BY created_at DESC LIMIT 10"
    )
    recent_alerts = recent_df.to_dict(orient="records") if not recent_df.empty else []

    return {
        "total_orders_today":        total_orders_today,
        "active_alerts_count":       active_alerts,
        "critical_alerts_count":     critical_alerts,
        "skus_at_risk":              skus_at_risk,
        "forecast_accuracy_percent": accuracy,
        "last_data_refresh":         last_refresh,
        "recent_alerts":             recent_alerts,
    }

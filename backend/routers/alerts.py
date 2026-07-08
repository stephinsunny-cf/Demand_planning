"""backend/routers/alerts.py — GET /api/alerts, POST /api/alerts/{id}/resolve"""

from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query

from backend.auth     import get_current_user, UserContext
from backend.database import query_df, get_db

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/alerts")
async def get_alerts(
    severity: Optional[str] = Query(default=None, description="CRITICAL, WARNING, INFO"),
    resolved: Optional[bool] = Query(default=False),
    user: UserContext = Depends(get_current_user),
):
    where = []
    if severity: where.append(f"severity = '{severity.upper()}'")
    if not resolved: where.append("resolved = 0")

    sql = f"""
        SELECT alert_id, alert_type, severity, message, sku, outlet, ingredient,
               created_at, resolved, resolved_at
        FROM alerts
        {'WHERE ' + ' AND '.join(where) if where else ''}
        ORDER BY
          CASE 
            WHEN severity = 'CRITICAL' THEN 0 
            WHEN severity = 'WARNING' THEN 1 
            ELSE 2 
          END,
          created_at DESC
        LIMIT 500
    """
    df = query_df(sql)
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    user: UserContext = Depends(get_current_user),
):
    resolved_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alerts SET resolved = 1, resolved_at = %s WHERE alert_id = %s",
                (resolved_at, alert_id)
            )
            conn.commit()
    return {"success": True, "alert_id": alert_id}

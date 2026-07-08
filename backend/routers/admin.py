"""backend/routers/admin.py — /api/admin/* (super_admin only)"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth     import require_role, UserContext
from backend.database import query_df, get_db

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


class CreateUserRequest(BaseModel):
    email: str
    role:  str

class UpdateUserRequest(BaseModel):
    role:   Optional[str] = None
    active: Optional[bool] = None

class ThresholdConfig(BaseModel):
    stockout_alert_pct: float = 10.0
    low_stock_days:     float = 2.0
    forecast_spike_pct: float = 50.0


@router.get("/admin/users")
async def list_users(user: UserContext = Depends(require_role("super_admin"))):
    """List all users from Supabase (requires service role key)."""
    import os
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        resp = sb.auth.admin.list_users()
        users = []
        for u in resp:
            users.append({
                "id":    u.id,
                "email": u.email,
                "role":  u.user_metadata.get("role", "demand_planner"),
                "created_at": str(u.created_at),
            })
        return users
    except Exception as exc:
        # Demo mode fallback
        return [
            {"id": "1", "email": "admin@curefoods.com", "role": "super_admin", "created_at": "2024-01-01"},
            {"id": "2", "email": "planner@curefoods.com", "role": "planning_manager", "created_at": "2024-01-02"},
        ]


@router.post("/admin/users")
async def create_user(
    body: CreateUserRequest,
    user: UserContext = Depends(require_role("super_admin")),
):
    import os
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        resp = sb.auth.admin.invite_user_by_email(body.email)
        sb.auth.admin.update_user_by_id(resp.user.id, {"user_metadata": {"role": body.role}})
        return {"success": True, "email": body.email, "role": body.role}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/admin/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    user: UserContext = Depends(require_role("super_admin")),
):
    import os
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        updates = {}
        if body.role:
            updates["user_metadata"] = {"role": body.role}
        if body.active is not None and not body.active:
            sb.auth.admin.delete_user(user_id)
            return {"success": True, "action": "deactivated"}
        sb.auth.admin.update_user_by_id(user_id, updates)
        return {"success": True, "user_id": user_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/thresholds")
async def get_thresholds(user: UserContext = Depends(require_role("super_admin"))):
    return {
        "stockout_alert_pct": 10.0,
        "low_stock_days":     2.0,
        "forecast_spike_pct": 50.0,
    }


@router.put("/admin/thresholds")
async def update_thresholds(
    body: ThresholdConfig,
    user: UserContext = Depends(require_role("super_admin")),
):
    # In production, store in Supabase settings table
    return {"success": True, "thresholds": body.model_dump()}


@router.get("/admin/pipeline-status")
async def get_pipeline_status(user: UserContext = Depends(require_role("super_admin"))):
    df = query_df("""
        SELECT job_name,
               max(started_at)   AS last_run,
               max(completed_at) AS last_completed,
               argMax(status, started_at) AS status,
               argMax(rows_processed, started_at) AS rows_processed,
               argMax(error_message, started_at) AS error_message
        FROM pipeline_runs
        GROUP BY job_name
        ORDER BY last_run DESC
    """)
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/admin/pipeline/trigger")
async def trigger_pipeline(user: UserContext = Depends(require_role("super_admin"))):
    """Manually trigger a full pipeline run (non-blocking)."""
    import threading
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    def run_in_background():
        from pipeline.main import run_full_pipeline
        use_dummy = __import__("os").getenv("USE_DUMMY_DATA", "false").lower() == "true"
        run_full_pipeline(use_dummy=use_dummy)

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()
    return {"success": True, "message": "Pipeline triggered in background"}

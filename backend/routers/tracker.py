from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.auth import get_current_user, UserContext, require_role
from backend.database import query_df, get_db_connection

router = APIRouter(prefix="/tracker", tags=["tracker"])

class TrackerItem(BaseModel):
    code: str
    ingredient: str
    supply_mode: Optional[str] = ""
    drr: Optional[float] = 0.0
    wh_sih: Optional[float] = 0.0
    open_po: Optional[float] = 0.0
    neworder: Optional[float] = 0.0
    lead_time_days: Optional[float] = 7.0

@router.get("")
async def get_tracked_items(
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner", "procurement"))
):
    df = query_df("""
        SELECT code, ingredient, supply_mode, drr, wh_sih, open_po, neworder, lead_time_days
        FROM procurement_tracker
        ORDER BY ingredient
    """)
    return df.to_dict(orient="records") if not df.empty else []

@router.post("")
async def add_tracked_item(
    item: TrackerItem,
    user: UserContext = Depends(require_role("super_admin", "planning_manager"))
):
    if not item.ingredient:
        raise HTTPException(status_code=400, detail="Ingredient name is required")
        
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO procurement_tracker (code, ingredient, supply_mode, drr, wh_sih, open_po, neworder, lead_time_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (item.code, item.ingredient, item.supply_mode, item.drr, item.wh_sih, item.open_po, item.neworder, item.lead_time_days))
            conn.commit()
        conn.close()
        return {"status": "success", "message": "Item added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

class LeadTimeUpdate(BaseModel):
    lead_time_days: float

@router.put("/{ingredient}/lead_time")
async def update_lead_time(
    ingredient: str,
    update: LeadTimeUpdate,
    user: UserContext = Depends(require_role("super_admin", "planning_manager"))
):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE procurement_tracker
                SET lead_time_days = %s
                WHERE ingredient = %s
            """, (update.lead_time_days, ingredient))
            conn.commit()
        conn.close()
        return {"status": "success", "message": "Lead time updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

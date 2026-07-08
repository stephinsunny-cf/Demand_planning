"""backend/routers/procurement.py — GET /api/procurement, POST /api/procurement/{id}/mark_ordered"""

import math
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import require_role, UserContext
from backend.database import query_df, get_db

router = APIRouter()


@router.get("/procurement")
async def get_procurement(
    vendor:   Optional[str] = Query(default=None),
    urgency:  Optional[str] = Query(default=None, description="URGENT or NORMAL"),
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "procurement")),
):
    where_clauses = []
    if vendor:
        where_clauses.append(f"lower(vendor_name) = lower('{vendor}')")
    if urgency:
        where_clauses.append(f"urgency = '{urgency.upper()}'")
        
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    df = query_df(f"""
        SELECT * 
        FROM fact_procurement
        WHERE {where_sql}
        ORDER BY 
            CASE WHEN urgency = 'URGENT' THEN 0 ELSE 1 END,
            vendor_name,
            ingredient
    """)
    
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/procurement/{ingredient}/mark_ordered")
async def mark_ordered(
    ingredient: str,
    user: UserContext = Depends(require_role("super_admin", "procurement")),
):
    # For now, update the PO status in fact_open_pos
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE fact_open_pos SET status = 'ordered' "
                f"WHERE lower(ingredient) = lower(%s) AND status = 'open'",
                (ingredient,)
            )
            conn.commit()
    return {"success": True, "ingredient": ingredient, "status": "marked_as_ordered"}

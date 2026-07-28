"""backend/routers/supply.py — GET /api/supply"""

import asyncio
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import get_current_user, UserContext, require_role
from backend.database import query_df

router = APIRouter()


@router.get("/supply")
async def get_supply_plan(
    kitchen: Optional[str] = Query(default=None),
    status:  Optional[str] = Query(default=None, description="RED, YELLOW, GREEN"),
    user: UserContext = Depends(require_role(
        "super_admin", "planning_manager", "demand_planner", "kitchen_ops"
    )),
):
    # Use the latest actual sales date as 'today' instead of the end of the future forecast
    max_date_df = await asyncio.to_thread(query_df, "SELECT max(date) as max_date FROM fact_daily_sales")
    if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
        today = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
    else:
        today = date.today()
        
    in_3d    = today + timedelta(days=3)

    plan = await asyncio.to_thread(query_df, """
        WITH forecast AS (
            SELECT f.ingredient AS sku_code, d.sku_name AS sku, f.outlet AS kitchen,
                   sum(f.total_qty_needed) AS forecast_3day
            FROM fact_ingredient_demand f
            JOIN dim_sku d ON f.ingredient = d.sku_code
            WHERE f.forecast_date >= %s AND f.forecast_date <= %s
            GROUP BY f.ingredient, d.sku_name, f.outlet
        ),
        latest_stock AS (
            SELECT kitchen, ingredient AS sku_code, sum(qty_available) AS stock_qty
            FROM fact_kitchen_stock s
            WHERE (kitchen, ingredient, snapshot_date) IN (
                SELECT kitchen, ingredient, max(snapshot_date)
                FROM fact_kitchen_stock
                WHERE (kitchen, ingredient) IN (SELECT kitchen, sku_code FROM forecast)
                GROUP BY kitchen, ingredient
            )
            GROUP BY kitchen, ingredient
        ),
        safety AS (
            SELECT sku, outlet AS kitchen, safety_stock_qty
            FROM dim_safety_stock
        )
        SELECT 
            f.sku_code, 
            f.sku, 
            f.kitchen, 
            f.forecast_3day,
            COALESCE(s.stock_qty, 0.0) AS stock_qty,
            COALESCE(sf.safety_stock_qty, 0.0) AS safety_stock_qty
        FROM forecast f
        LEFT JOIN latest_stock s ON f.kitchen = s.kitchen AND f.sku_code = s.sku_code
        LEFT JOIN safety sf ON f.sku = sf.sku AND f.kitchen = sf.kitchen
    """, params=(today, in_3d))

    if plan.empty:
        return []

    plan["replenishment_needed"] = (
        plan["forecast_3day"] + plan["safety_stock_qty"] - plan["stock_qty"]
    ).clip(lower=0).round(2)

    def classify(row):
        if row["replenishment_needed"] <= 0:
            return "GREEN"
        elif row["forecast_3day"] > 0 and row["replenishment_needed"] > 0.5 * row["forecast_3day"]:
            return "RED"
        return "YELLOW"

    plan["status"] = plan.apply(classify, axis=1)

    # Filters
    if kitchen:
        plan = plan[plan["kitchen"].str.lower() == kitchen.lower()]
    if status:
        plan = plan[plan["status"] == status.upper()]

    # Sort: RED first
    status_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    plan["_s"] = plan["status"].map(status_order)
    plan = plan.sort_values("_s").drop(columns=["_s"])

    return plan.to_dict(orient="records")

"""backend/routers/supply.py — GET /api/supply"""

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
    max_date_df = query_df("SELECT max(forecast_date) as max_date FROM fact_forecast")
    if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
        today = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
    else:
        today = date.today()
        
    in_3d    = today + timedelta(days=3)

    # 3-day ingredient demand per kitchen
    fore_df = query_df(f"""
        SELECT f.ingredient AS sku, f.outlet AS kitchen,
               sum(f.total_qty_needed) AS forecast_3day
        FROM fact_ingredient_demand f
        JOIN procurement_tracker pt ON lower(f.ingredient) = lower(pt.code)
        WHERE f.forecast_date >= '{today}' AND f.forecast_date <= '{in_3d}'
        GROUP BY f.ingredient, f.outlet
    """)

    # Latest kitchen stock
    stock_df = query_df("""
        SELECT kitchen, ingredient AS sku, sum(qty_available) AS stock_qty
        FROM fact_kitchen_stock
        WHERE (kitchen, ingredient, snapshot_date) IN (
          SELECT kitchen, ingredient, max(snapshot_date)
          FROM fact_kitchen_stock GROUP BY kitchen, ingredient
        ) GROUP BY kitchen, ingredient
    """)

    # Safety stock defaults
    safety_df = query_df("""
        SELECT sku, outlet AS kitchen, safety_stock_qty
        FROM dim_safety_stock
    """)

    if fore_df.empty:
        return []

    import pandas as pd
    plan = fore_df.copy()
    if not stock_df.empty:
        plan = plan.merge(stock_df, on=["sku", "kitchen"], how="left")
    else:
        plan["stock_qty"] = 0.0
    plan["stock_qty"] = plan["stock_qty"].fillna(0.0)

    if not safety_df.empty:
        plan = plan.merge(safety_df, on=["sku", "kitchen"], how="left")
    else:
        plan["safety_stock_qty"] = 0.0
    plan["safety_stock_qty"] = plan.get("safety_stock_qty", 0).fillna(0.0)

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

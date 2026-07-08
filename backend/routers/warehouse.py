"""backend/routers/warehouse.py — GET /api/warehouse"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import require_role, UserContext
from backend.database import query_df

router = APIRouter()


@router.get("/warehouse")
async def get_warehouse(
    status:     Optional[str] = Query(default=None, description="RED, YELLOW, GREEN"),
    ingredient: Optional[str] = Query(default=None),
    user: UserContext = Depends(require_role(
        "super_admin", "planning_manager", "demand_planner", "procurement"
    )),
):
    import pandas as pd

    # Ingredient demand (from recipe master × forecast)
    demand_df = query_df("""
        SELECT r.ingredient, r.unit,
               sum(r.qty_per_portion / r.yield_factor) AS demand_per_unit
        FROM dim_recipe_master r
        GROUP BY r.ingredient, r.unit
    """)

    # Latest warehouse stock
    stock_df = query_df("""
        SELECT ingredient, sum(qty_available) AS warehouse_stock, unit
        FROM fact_warehouse_stock
        WHERE (warehouse, ingredient, snapshot_time) IN (
          SELECT warehouse, ingredient, max(snapshot_time)
          FROM fact_warehouse_stock GROUP BY warehouse, ingredient
        )
        GROUP BY ingredient, unit
    """)

    if demand_df.empty:
        return []

    demand_df["ingredient"] = demand_df["ingredient"].astype(str).str.strip().str.lower()
    stock_df["ingredient"]  = stock_df["ingredient"].astype(str).str.strip().str.lower() if not stock_df.empty else stock_df.get("ingredient", pd.Series())

    report = demand_df.merge(
        stock_df[["ingredient", "warehouse_stock"]] if not stock_df.empty else pd.DataFrame(columns=["ingredient", "warehouse_stock"]),
        on="ingredient", how="left"
    )
    report["warehouse_stock"]  = report["warehouse_stock"].fillna(0.0)
    report["net_requirement"]  = (report["demand_per_unit"] - report["warehouse_stock"]).round(2)
    report = report.rename(columns={"demand_per_unit": "total_qty_needed"})

    def classify(row):
        if row["net_requirement"] > 0:
            return "RED"
        remaining = row["warehouse_stock"] - row["total_qty_needed"]
        if row["total_qty_needed"] > 0 and remaining / max(row["total_qty_needed"], 1) < 0.1:
            return "YELLOW"
        return "GREEN"

    report["status"] = report.apply(classify, axis=1)

    if status:
        report = report[report["status"] == status.upper()]
    if ingredient:
        report = report[report["ingredient"].str.contains(ingredient.lower(), case=False, na=False)]

    status_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    report["_s"] = report["status"].map(status_order)
    report = report.sort_values("_s").drop(columns=["_s"])

    return report.to_dict(orient="records")

"""
pipeline/engines/warehouse_planning.py — ENGINE 5
────────────────────────────────────────────────────
Compares ingredient demand (from recipe explosion) against warehouse stock.
Produces a shortage report per ingredient.

Formula: Net Requirement = Total Ingredient Demand − Warehouse Stock

Warehouse locations are identified by keywords in the location name:
  warehouse, WH, hub, central, store, cluster kitchen

Status:
  RED    → net_requirement > 0 (actual shortage)
  YELLOW → net_requirement <= 0 but stock < 10% buffer above demand
  GREEN  → sufficient stock
"""

import logging
from datetime import datetime, timezone, timedelta

import pandas as pd

from backend.database import query_df

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

LOW_STOCK_THRESHOLD = 0.10  # 10% of demand = low stock warning

# Keywords that identify a warehouse/hub location vs a kitchen
WAREHOUSE_KEYWORDS = ["warehouse", " wh", "wh ", "_wh", "hub", "central",
                      "cluster store", "cluster kitchen", "store/wh", "smoodies_store"]


def _is_warehouse(name: str) -> bool:
    """Return True if location name looks like a warehouse/hub."""
    lower = name.lower()
    return any(kw in lower for kw in WAREHOUSE_KEYWORDS)


def run(ingredient_demand: pd.DataFrame = None) -> pd.DataFrame:
    """
    Run warehouse planning engine.

    Args:
        ingredient_demand: output from recipe_explosion.run()
                           (columns: ingredient, unit, total_qty_needed)
                           If None, loads from DB directly.

    Returns:
        Shortage report DataFrame.
    """
    started_at = datetime.now(IST)
    log.info("=" * 60)
    log.info("ENGINE 5: Warehouse Planning — start")

    try:
        # Pull latest warehouse stock from fact_kitchen_stock
        # (which contains both kitchen and warehouse locations from SupplyNote)
        stock_df = query_df("""
            SELECT kitchen, ingredient, qty_available, unit
            FROM fact_kitchen_stock
            WHERE (kitchen, ingredient, snapshot_date) IN (
                SELECT kitchen, ingredient, max(snapshot_date)
                FROM fact_kitchen_stock
                GROUP BY kitchen, ingredient
            )
        """)

        if stock_df.empty:
            log.warning("Stock table is empty — treating all warehouse stock as zero")
            stock_df = pd.DataFrame(columns=["kitchen", "ingredient", "qty_available", "unit"])

        # Filter to warehouse locations only
        stock_df["is_warehouse"] = stock_df["kitchen"].apply(_is_warehouse)
        warehouse_stock = stock_df[stock_df["is_warehouse"]].copy()
        log.info("Warehouse locations found: %d distinct", warehouse_stock["kitchen"].nunique())

        # Aggregate warehouse stock by ingredient across all warehouses
        if not warehouse_stock.empty:
            stock_agg = warehouse_stock.groupby("ingredient", as_index=False).agg(
                warehouse_stock=("qty_available", "sum"),
                unit=("unit", "first"),
            )
        else:
            log.warning("No warehouse locations found in stock — treating all as zero")
            stock_agg = pd.DataFrame(columns=["ingredient", "warehouse_stock", "unit"])

        # If no ingredient_demand passed, we can't calculate — return stock snapshot
        if ingredient_demand is None or ingredient_demand.empty:
            log.warning("No ingredient demand data — returning warehouse stock snapshot only")
            if not stock_agg.empty:
                stock_agg["total_qty_needed"] = 0.0
                stock_agg["net_requirement"] = 0.0
                stock_agg["status"] = "GREEN"
            return stock_agg

        # Normalise ingredient names for join
        ingredient_demand = ingredient_demand.copy()
        ingredient_demand["ingredient"] = ingredient_demand["ingredient"].astype(str).str.strip().str.lower()
        stock_agg["ingredient"] = stock_agg["ingredient"].astype(str).str.strip().str.lower()

        # Merge demand with warehouse stock
        report = ingredient_demand.merge(
            stock_agg[["ingredient", "warehouse_stock"]],
            on="ingredient",
            how="left"
        )
        report["warehouse_stock"] = report["warehouse_stock"].fillna(0.0)

        # Net requirement = Ingredient Demand − Warehouse Stock
        report["net_requirement"] = (report["total_qty_needed"] - report["warehouse_stock"]).clip(lower=0).round(2)

        # Status
        def classify(row):
            if row["net_requirement"] > 0:
                return "RED"
            remaining = row["warehouse_stock"] - row["total_qty_needed"]
            if row["total_qty_needed"] > 0 and remaining / row["total_qty_needed"] < LOW_STOCK_THRESHOLD:
                return "YELLOW"
            return "GREEN"

        report["status"] = report.apply(classify, axis=1)

        # Sort: RED first
        status_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
        report["_sort"] = report["status"].map(status_order)
        report = report.sort_values("_sort").drop(columns=["_sort"])

        for col in ["total_qty_needed", "warehouse_stock", "net_requirement"]:
            if col in report.columns:
                report[col] = report[col].round(2)

        log.info("Warehouse plan: %d ingredients | RED=%d YELLOW=%d GREEN=%d",
                 len(report),
                 (report["status"] == "RED").sum(),
                 (report["status"] == "YELLOW").sum(),
                 (report["status"] == "GREEN").sum())

        return report

    except Exception as exc:
        log.error("Warehouse planning engine failed: %s", exc, exc_info=True)
        return pd.DataFrame()

"""
pipeline/engines/supply_planning.py — ENGINE 3
────────────────────────────────────────────────
Internal supply planning: calculates replenishment needed per kitchen per SKU.

Formula: Replenishment = Forecast Demand + Safety Stock − Current Kitchen Stock
Status:
  RED    → replenishment > 50% of forecast
  YELLOW → replenishment > 0 and ≤ 50% of forecast
  GREEN  → no replenishment needed
"""

import logging
from datetime import datetime, timezone, timedelta, date

import pandas as pd
import numpy as np

# Use Postgres instead of ClickHouse
from backend.database import query_df

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SAFETY_STOCK_DAYS = 7.0

def log_pipeline_run(job_name: str, started_at: datetime, status: str, rows_processed: int = 0, error_message: str = ""):
    pass # Disabling logging for now until pipeline_runs is created in PG

def run() -> pd.DataFrame:
    """
    Run supply planning engine.
    Returns supply plan DataFrame with replenishment status per SKU × kitchen.
    """
    started_at = datetime.now(IST)
    log.info("=" * 60)
    log.info("ENGINE 3: Supply Planning — start")

    try:
        # Load 3-day forecast per SKU × outlet
        today = date.today()
        in_3_days = today + timedelta(days=3)

        forecast_df = query_df(
            f"SELECT sku, outlet, sum(qty_predicted) AS forecast_3day "
            f"FROM fact_forecast "
            f"WHERE forecast_date >= '{today}' AND forecast_date <= '{in_3_days}' "
            f"GROUP BY sku, outlet"
        )

        # Latest kitchen stock snapshot
        stock_df = query_df(
            "SELECT kitchen, ingredient AS sku, qty_available AS stock_qty, unit "
            "FROM fact_kitchen_stock "
            "WHERE (kitchen, ingredient, snapshot_date) IN ("
            "  SELECT kitchen, ingredient, max(snapshot_date) "
            "  FROM fact_kitchen_stock "
            "  GROUP BY kitchen, ingredient"
            ")"
        )

        # Dynamic Lead Time settings from Procurement Tracker
        safety_df = query_df(
            "SELECT ingredient AS sku, lead_time_days AS safety_stock_days "
            "FROM procurement_tracker"
        )

        # Average daily sales for safety stock calculation
        avg_sales_df = query_df(
            "SELECT sku, outlet, avg(qty_sold) AS avg_daily_qty "
            "FROM fact_daily_sales "
            f"WHERE date >= '{today - timedelta(days=28)}' "
            "GROUP BY sku, outlet"
        )

        if forecast_df.empty:
            log.warning("No forecast data — run forecast engine first")
            return pd.DataFrame()

        # Merge forecast with kitchen stock
        plan = forecast_df.copy()
        plan = plan.rename(columns={"outlet": "kitchen"})

        # Merge with stock
        if not stock_df.empty:
            stock_agg = stock_df.groupby(["kitchen", "sku"], as_index=False)["stock_qty"].sum()
            plan = plan.merge(stock_agg, on=["sku", "kitchen"], how="left")
        else:
            plan["stock_qty"] = 0.0

        # Merge with average sales for safety stock
        if not avg_sales_df.empty:
            avg_sales = avg_sales_df.rename(columns={"outlet": "kitchen"})
            plan = plan.merge(avg_sales, on=["sku", "kitchen"], how="left")
        else:
            plan["avg_daily_qty"] = 0.0

        # Merge with custom safety stock settings (Lead time)
        if not safety_df.empty:
            # Cross join since procurement_tracker doesn't have kitchen/outlet
            safety_df['key'] = 1
            plan['key'] = 1
            # We don't need cross join if we just merge on sku
            safety = safety_df.drop(columns=['key'], errors='ignore')
            plan = plan.drop(columns=['key'], errors='ignore')
            plan = plan.merge(safety, on=["sku"], how="left")
        else:
            plan["safety_stock_days"] = DEFAULT_SAFETY_STOCK_DAYS

        # Fill nulls
        plan["stock_qty"]          = plan["stock_qty"].fillna(0.0)
        plan["avg_daily_qty"]      = plan["avg_daily_qty"].fillna(0.0)
        plan["safety_stock_days"]  = plan["safety_stock_days"].fillna(DEFAULT_SAFETY_STOCK_DAYS)

        # Calculate safety stock qty dynamically: DRR * Lead Time
        plan["safety_stock_qty"] = plan["avg_daily_qty"] * plan["safety_stock_days"]

        # Replenishment = forecast + safety_stock - current_stock
        plan["replenishment_needed"] = (
            plan["forecast_3day"] + plan["safety_stock_qty"] - plan["stock_qty"]
        ).clip(lower=0)

        # Status classification
        def classify_status(row):
            if row["replenishment_needed"] <= 0:
                return "GREEN"
            elif row["forecast_3day"] > 0 and row["replenishment_needed"] > 0.5 * row["forecast_3day"]:
                return "RED"
            else:
                return "YELLOW"

        plan["status"] = plan.apply(classify_status, axis=1)

        # Round for display
        for col in ["forecast_3day", "stock_qty", "safety_stock_qty", "replenishment_needed"]:
            plan[col] = plan[col].round(2)

        # Sort: RED first, then YELLOW, then GREEN
        status_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
        plan["_sort"] = plan["status"].map(status_order)
        plan = plan.sort_values("_sort").drop(columns=["_sort"])

        log.info("Supply plan: %d rows | RED=%d YELLOW=%d GREEN=%d",
                 len(plan),
                 (plan["status"] == "RED").sum(),
                 (plan["status"] == "YELLOW").sum(),
                 (plan["status"] == "GREEN").sum())

        log_pipeline_run("supply_planning", started_at, "SUCCESS", len(plan))
        return plan

    except Exception as exc:
        log.error("Supply planning engine failed: %s", exc, exc_info=True)
        log_pipeline_run("supply_planning", started_at, "ERROR", 0, str(exc))
        return pd.DataFrame()

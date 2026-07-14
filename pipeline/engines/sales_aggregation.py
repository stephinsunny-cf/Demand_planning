"""
pipeline/engines/sales_aggregation.py — ENGINE 1
───────────────────────────────────────────────────
Joins orders + order_items, groups by date/sku/brand/outlet/city,
and writes aggregated daily sales to fact_daily_sales.

Business rule: Only completed/delivered orders are counted.
"""

import logging
from datetime import datetime, timezone, timedelta

import pandas as pd

from pipeline.loaders.postgres import insert_df, query_df, get_local_client, log_pipeline_run

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def run(orders_df: pd.DataFrame = None, items_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Run sales aggregation engine.

    If orders_df / items_df are not provided, reads from local PostgreSQL staging tables.
    Returns the aggregated fact_daily_sales DataFrame.
    """
    started_at = datetime.now(IST)
    log.info("=" * 60)
    log.info("ENGINE 1: Sales Aggregation — start")

    try:
        client = get_local_client()

        # Load data from staging if not passed in
        if orders_df is None:
            orders_df = query_df(
                "SELECT order_id, created_at, store_name, brand, status, total, city "
                "FROM fact_orders_raw",
                client=client,
            )
        if items_df is None:
            items_df = query_df(
                "SELECT id, order_id, item_name, quantity, price "
                "FROM fact_order_items_raw",
                client=client,
            )

        if orders_df.empty or items_df.empty:
            log.warning("Orders or items data is empty — skipping sales aggregation")
            log_pipeline_run("sales_aggregation", started_at, "SKIPPED", 0, "Empty input data", client)
            client.close()
            return pd.DataFrame()

        # Filter completed orders only (belt-and-suspenders — already done in clean step)
        completed = {"completed", "delivered", "complete", "fulfilled"}
        if "status" in orders_df.columns:
            orders_df = orders_df[orders_df["status"].str.lower().isin(completed)]

        # Drop created_at from items_df to avoid suffixing issues during merge
        if "created_at" in items_df.columns:
            items_df = items_df.drop(columns=["created_at"])
            
        # Join items to orders to get brand, outlet, city, date
        merged = items_df.merge(
            orders_df[["order_id", "created_at", "store_name", "brand", "city"]],
            on="order_id",
            how="inner",
        )

        if merged.empty:
            log.warning("No matching orders/items after join — check order_id linkage")
            log_pipeline_run("sales_aggregation", started_at, "SKIPPED", 0, "Empty join result", client)
            client.close()
            return pd.DataFrame()

        # Extract date from timestamp
        merged["date"] = pd.to_datetime(merged["created_at"]).dt.date

        # Ensure numeric types
        merged["quantity"] = pd.to_numeric(merged["quantity"], errors="coerce").fillna(0)
        merged["price"]    = pd.to_numeric(merged["price"], errors="coerce").fillna(0)
        merged["revenue"]  = merged["quantity"] * merged["price"]

        # Standardise SKU name
        merged["sku"] = (
            merged["item_name"]
            .astype(str)
            .str.strip()
            .str.lower()
        )
        merged["outlet"] = merged["store_name"].astype(str).str.strip()

        # Aggregate strictly to PostgreSQL PK grain
        agg = (
            merged.groupby(["date", "sku", "outlet"], as_index=False)
            .agg(
                brand       =("brand", "first"),
                city        =("city", "first"),
                qty_sold    =("quantity", "sum"),
                revenue     =("revenue", "sum"),
                order_count =("order_id", "nunique"),
            )
        )

        # Cast types
        agg["date"]        = pd.to_datetime(agg["date"]).dt.date
        agg["qty_sold"]    = agg["qty_sold"].astype(float)
        agg["revenue"]     = agg["revenue"].round(2).astype(float)
        agg["order_count"] = agg["order_count"].astype(int)

        # Filter out zero sales rows
        agg = agg[agg["qty_sold"] > 0]

        log.info("Sales aggregation: %d daily sales rows for %d unique SKUs across %d outlets",
                 len(agg),
                 agg["sku"].nunique(),
                 agg["outlet"].nunique())

        # Write to PostgreSQL
        rows_inserted = insert_df(agg, "fact_daily_sales", client=client)
        log_pipeline_run("sales_aggregation", started_at, "SUCCESS", rows_inserted, client=client)
        client.close()

        return agg

    except Exception as exc:
        log.error("Sales aggregation engine failed: %s", exc, exc_info=True)
        log_pipeline_run("sales_aggregation", started_at, "ERROR", 0, str(exc))
        return pd.DataFrame()

"""
pipeline/engines/procurement_engine.py — ENGINE 6
────────────────────────────────────────────────────
Generates purchase recommendations per vendor per ingredient based on Warehouse Planning.

Formula: Procurement Qty = (Net Req (Warehouse) + Safety Stock) - Open PO Qty
         Where Net Req (Warehouse) = Total Ingredient Demand - Warehouse Stock
         Then round UP to nearest MOQ.
"""

import logging
import math
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone, timedelta, date

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import query_df, get_db_connection

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

SAFETY_BUFFER_DAYS = 7  # 1 week safety buffer for procurement

def _round_up_to_moq(qty: float, moq: float) -> float:
    """Round quantity UP to the nearest multiple of MOQ."""
    if moq <= 0:
        moq = 1.0
    if qty <= 0:
        return 0.0
    return math.ceil(qty / moq) * moq

def run() -> pd.DataFrame:
    started_at = datetime.now(IST)
    print("=" * 60)
    print("ENGINE 6: Procurement Engine - start")

    try:
        # 1. Total Ingredient Demand (Next 7 days, sum across all outlets)
        today = date.today()
        in_7_days = today + timedelta(days=7)
        demand_df = query_df(f"""
            SELECT ingredient, unit, sum(total_qty_needed) AS total_demand
            FROM fact_ingredient_demand
            WHERE forecast_date >= '{today}' AND forecast_date <= '{in_7_days}'
            GROUP BY ingredient, unit
        """)

        # 2. Warehouse Stock
        # Identify warehouse locations from fact_kitchen_stock
        stock_df = query_df("""
            SELECT ingredient, sum(qty_available) AS warehouse_stock
            FROM fact_kitchen_stock
            WHERE lower(kitchen) LIKE '%warehouse%' 
               OR lower(kitchen) LIKE '% wh %'
               OR lower(kitchen) LIKE '%_wh%'
               OR lower(kitchen) LIKE '%hub%'
               OR lower(kitchen) LIKE '%central%'
               OR lower(kitchen) LIKE '%commissary%'
            GROUP BY ingredient
        """)

        # 3. Open POs
        pos_df = query_df("""
            SELECT ingredient, sum(qty_ordered) AS po_qty
            FROM fact_open_pos
            WHERE status = 'open'
            GROUP BY ingredient
        """)

        # 4. Vendor master (lead times, MOQs, prices)
        vendor_df = query_df("""
            SELECT 'Default Vendor' AS vendor_name, ingredient, lead_time_days, 1 AS moq, 'KG' AS unit, 100 AS price
            FROM procurement_tracker
        """)

        if demand_df.empty:
            print("No demand data found.")
            return pd.DataFrame()

        # Normalise ingredient names
        demand_df["ingredient"] = demand_df["ingredient"].astype(str).str.strip().str.lower()
        if not stock_df.empty:
            stock_df["ingredient"] = stock_df["ingredient"].astype(str).str.strip().str.lower()
        if not pos_df.empty:
            pos_df["ingredient"] = pos_df["ingredient"].astype(str).str.strip().str.lower()
        if not vendor_df.empty:
            vendor_df["ingredient"] = vendor_df["ingredient"].astype(str).str.strip().str.lower()

        # Merge Data
        recs = demand_df.copy()
        
        # Merge Warehouse Stock
        if not stock_df.empty:
            recs = recs.merge(stock_df, on="ingredient", how="left")
        else:
            recs["warehouse_stock"] = 0.0
        recs["warehouse_stock"] = recs["warehouse_stock"].fillna(0.0)

        # Calculate Net Requirement
        recs["net_requirement"] = (recs["total_demand"] - recs["warehouse_stock"]).clip(lower=0)

        # Calculate average daily demand for safety stock
        recs["avg_daily"] = recs["total_demand"] / 7.0
        recs["safety_buffer"] = recs["avg_daily"] * SAFETY_BUFFER_DAYS

        # Merge Open POs
        if not pos_df.empty:
            recs = recs.merge(pos_df, on="ingredient", how="left")
        else:
            recs["po_qty"] = 0.0
        recs["po_qty"] = recs["po_qty"].fillna(0.0)

        # Merge Vendor Data
        if not vendor_df.empty:
            recs = recs.merge(vendor_df, on="ingredient", how="left", suffixes=("", "_vendor"))
        else:
            recs["lead_time_days"] = 3
            recs["moq"] = 1.0
            recs["price"] = 0.0
            recs["vendor_name"] = "Unknown Vendor"

        recs["lead_time_days"] = pd.to_numeric(recs.get("lead_time_days", 3), errors="coerce").fillna(3).astype(int)
        recs["moq"]            = pd.to_numeric(recs.get("moq", 1.0), errors="coerce").fillna(1.0)
        recs["price"]          = pd.to_numeric(recs.get("price", 0.0), errors="coerce").fillna(0.0)
        recs["vendor_name"]    = recs.get("vendor_name", "Unknown Vendor").fillna("Unknown Vendor")

        # Procurement Qty = (Net Req + Safety Stock) - Open PO Qty
        recs["raw_recommended_qty"] = (recs["net_requirement"] + recs["safety_buffer"]) - recs["po_qty"]
        recs["recommended_qty"] = recs.apply(
            lambda r: _round_up_to_moq(r["raw_recommended_qty"], r["moq"]), axis=1
        )

        # Filter out 0 recommended
        recs = recs[recs["recommended_qty"] > 0]

        if recs.empty:
            print("No procurement needed - all shortages covered.")
            return pd.DataFrame()

        # Final Formatting
        recs["estimated_cost"] = (recs["recommended_qty"] * recs["price"]).round(2)
        recs["expected_delivery"] = recs["lead_time_days"].apply(
            lambda d: str(today + timedelta(days=int(d)))
        )
        recs["urgency"] = recs.apply(
            lambda r: "URGENT" if r["warehouse_stock"] <= 0 and r["total_demand"] > 0 else "NORMAL", axis=1
        )

        for col in ["total_demand", "warehouse_stock", "net_requirement", "safety_buffer", "po_qty", "recommended_qty"]:
            recs[col] = recs[col].round(2)

        print(f"Generated {len(recs)} procurement recommendations.")

        # Write to Postgres
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fact_procurement (
                        ingredient VARCHAR(255),
                        unit VARCHAR(50),
                        total_demand FLOAT,
                        warehouse_stock FLOAT,
                        net_requirement FLOAT,
                        safety_buffer FLOAT,
                        po_qty FLOAT,
                        vendor_name VARCHAR(255),
                        lead_time_days INT,
                        moq FLOAT,
                        price FLOAT,
                        recommended_qty FLOAT,
                        estimated_cost FLOAT,
                        expected_delivery VARCHAR(50),
                        urgency VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("TRUNCATE TABLE fact_procurement")
                
                insert_query = """
                    INSERT INTO fact_procurement (
                        ingredient, unit, total_demand, warehouse_stock, net_requirement,
                        safety_buffer, po_qty, vendor_name, lead_time_days, moq, price,
                        recommended_qty, estimated_cost, expected_delivery, urgency
                    ) VALUES %s
                """
                values = [
                    (r['ingredient'], r['unit'], r['total_demand'], r['warehouse_stock'], r['net_requirement'],
                     r['safety_buffer'], r['po_qty'], r['vendor_name'], r['lead_time_days'], r['moq'], r['price'],
                     r['recommended_qty'], r['estimated_cost'], r['expected_delivery'], r['urgency'])
                    for _, r in recs.iterrows()
                ]
                execute_values(cur, insert_query, values)
                conn.commit()
                print("Successfully updated fact_procurement table!")

        return recs

    except Exception as exc:
        print(f"Procurement engine failed: {exc}")
        return pd.DataFrame()

if __name__ == "__main__":
    run()

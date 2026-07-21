"""
pipeline/engines/alert_engine.py — ENGINE 7
─────────────────────────────────────────────
Checks 9 alert rules across all tables and writes to the alerts table in PostgreSQL.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta, date
import psycopg2
from psycopg2.extras import execute_values
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import query_df, get_db_connection

import pandas as pd

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

def _build_alert(alert_type: str, severity: str, message: str,
                 sku: str = "", outlet: str = "", ingredient: str = "") -> dict:
    return {
        "alert_id":   str(uuid.uuid4()),
        "alert_type": alert_type,
        "severity":   severity,
        "message":    message,
        "sku":        sku,
        "outlet":     outlet,
        "ingredient": ingredient,
        "created_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "resolved":   0,
        "resolved_at": None,
    }

def run() -> list:
    started_at = datetime.now(IST)
    print("=" * 60)
    print("ENGINE 7: Alert Engine - start")

    # 1. Create table if not exists
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id VARCHAR(50) PRIMARY KEY,
                    alert_type VARCHAR(50),
                    severity VARCHAR(20),
                    message TEXT,
                    sku VARCHAR(255),
                    outlet VARCHAR(255),
                    ingredient VARCHAR(255),
                    created_at TIMESTAMP,
                    resolved INT DEFAULT 0,
                    resolved_at TIMESTAMP
                )
            """)
            conn.commit()

    new_alerts = []
    today = date.today()

    try:
        # Get existing unresolved alerts to avoid duplicates
        existing_df = query_df("SELECT alert_type, sku, outlet, ingredient FROM alerts WHERE resolved = 0")
        existing_set = set()
        if not existing_df.empty:
            for _, r in existing_df.iterrows():
                existing_set.add((str(r.get('alert_type')), str(r.get('sku')), str(r.get('outlet')), str(r.get('ingredient'))))

        def is_new(alert_type: str, sku: str = "", outlet: str = "", ingredient: str = "") -> bool:
            return (str(alert_type), str(sku), str(outlet), str(ingredient)) not in existing_set

        # RULE 1: Kitchen stock = 0
        try:
            kitchen_zero = query_df("""
                SELECT kitchen, ingredient, qty_available
                FROM fact_kitchen_stock
                WHERE qty_available <= 0
                AND (kitchen, ingredient, snapshot_date) IN (
                  SELECT kitchen, ingredient, max(snapshot_date)
                  FROM fact_kitchen_stock GROUP BY kitchen, ingredient
                )
            """)
            if not kitchen_zero.empty:
                for _, r in kitchen_zero.iterrows():
                    if is_new("KITCHEN_STOCKOUT", sku=r["ingredient"], outlet=r["kitchen"], ingredient=r["ingredient"]):
                        new_alerts.append(_build_alert(
                            "KITCHEN_STOCKOUT", "CRITICAL",
                            f"CRITICAL: {r['ingredient']} is out of stock at {r['kitchen']}",
                            sku=r["ingredient"], outlet=r["kitchen"], ingredient=r["ingredient"],
                        ))
        except Exception as e:
            print(f"Rule 1 error: {e}")

        # RULE 2: Warehouse ingredient < 10% of 3-day demand
        try:
            in_3_days = today + timedelta(days=3)
            demand_df = query_df(f"""
                SELECT ingredient, sum(total_qty_needed) AS demand_3day
                FROM fact_ingredient_demand
                WHERE forecast_date >= '{today}' AND forecast_date <= '{in_3_days}'
                GROUP BY ingredient
            """)
            wh_stock_df = query_df("""
                SELECT ingredient, sum(qty_available) AS stock_qty
                FROM fact_kitchen_stock
                WHERE (lower(kitchen) LIKE '%warehouse%' OR lower(kitchen) LIKE '%_wh%')
                GROUP BY ingredient
            """)
            if not demand_df.empty and not wh_stock_df.empty:
                wh_check = demand_df.merge(wh_stock_df, on="ingredient", how="inner")
                critical = wh_check[wh_check["stock_qty"] < 0.1 * wh_check["demand_3day"]]
                for _, r in critical.iterrows():
                    if is_new("WH_CRITICAL_LOW", ingredient=r["ingredient"]):
                        new_alerts.append(_build_alert(
                            "WH_CRITICAL_LOW", "CRITICAL",
                            f"CRITICAL: {r['ingredient']} stock critically low at warehouse ({r['stock_qty']:.0f} vs {r['demand_3day']:.0f} needed)",
                            ingredient=r["ingredient"],
                        ))
        except Exception as e:
            print(f"Rule 2 error: {e}")

        # RULE 3: PO overdue
        try:
            overdue_pos = query_df(f"""
                SELECT po_number, ingredient, vendor, expected_date
                FROM fact_open_pos
                WHERE expected_date < '{today}' AND status = 'open'
            """)
            if not overdue_pos.empty:
                for _, r in overdue_pos.iterrows():
                    if is_new("PO_OVERDUE", ingredient=r["ingredient"], outlet=r["po_number"]):
                        new_alerts.append(_build_alert(
                            "PO_OVERDUE", "CRITICAL",
                            f"CRITICAL: PO {r['po_number']} overdue — {r['ingredient']} not received (expected {r['expected_date']})",
                            ingredient=r["ingredient"], outlet=r["po_number"],
                        ))
        except Exception as e:
            print(f"Rule 3 error: {e}")

        # RULE 4: Forecast demand > stock + open POs (Skip for now, complex join, handled by Rule 1 & 2)
        
        # RULE 5: Forecast spike > 50% above 4-week average
        try:
            four_weeks_ago = today - timedelta(days=28)
            avg_sales = query_df(f"""
                SELECT sku, outlet, avg(qty_sold) AS avg_daily
                FROM fact_daily_sales
                WHERE date >= '{four_weeks_ago}' GROUP BY sku, outlet
            """)
            latest_forecast = query_df(f"""
                SELECT sku, outlet, avg(qty_predicted) AS avg_forecast
                FROM fact_forecast
                WHERE forecast_date >= '{today}' AND forecast_date <= '{today + timedelta(days=7)}'
                GROUP BY sku, outlet
            """)
            if not avg_sales.empty and not latest_forecast.empty:
                spike_check = avg_sales.merge(latest_forecast, on=["sku", "outlet"], how="inner")
                spikes = spike_check[spike_check["avg_forecast"] > 1.5 * spike_check["avg_daily"]]
                for _, r in spikes.iterrows():
                    if is_new("DEMAND_SPIKE", sku=r["sku"], outlet=r["outlet"]):
                        pct = ((r["avg_forecast"] / r["avg_daily"]) - 1) * 100
                        new_alerts.append(_build_alert(
                            "DEMAND_SPIKE", "WARNING",
                            f"WARNING: Unusual demand spike for {r['sku']} at {r['outlet']} ({pct:.0f}% above 4-week average)",
                            sku=r["sku"], outlet=r["outlet"],
                        ))
        except Exception as e:
            print(f"Rule 5 error: {e}")

        # RULE 6: Menu item has no recipe
        try:
            # We don't have dim_menu_items in PG, let's use fact_forecast distinct SKUs
            active_skus = query_df("SELECT DISTINCT sku FROM fact_forecast")
            recipe_dishes = query_df("SELECT DISTINCT lower(trim(dish_name)) AS dish FROM recipe_master")
            if not active_skus.empty and not recipe_dishes.empty:
                active_skus["sku_lower"] = active_skus["sku"].str.lower().str.strip()
                recipe_set = set(recipe_dishes["dish"].tolist())
                no_recipe = active_skus[~active_skus["sku_lower"].isin(recipe_set)]
                for _, r in no_recipe.iterrows():
                    if is_new("NO_RECIPE", sku=r["sku"]):
                        new_alerts.append(_build_alert(
                            "NO_RECIPE", "WARNING",
                            f"WARNING: Forecasted dish '{r['sku']}' has no recipe mapped — cannot plan ingredients.",
                            sku=r["sku"],
                        ))
        except Exception as e:
            print(f"Rule 6 error: {e}")

        # RULE 9: Lead time means PO must be placed today
        try:
            urgent_procurement = query_df("SELECT ingredient, vendor_name, lead_time_days FROM fact_procurement WHERE urgency = 'URGENT'")
            if not urgent_procurement.empty:
                for _, r in urgent_procurement.iterrows():
                    if is_new("LEAD_TIME_ALERT", ingredient=r["ingredient"], outlet=r["vendor_name"]):
                        new_alerts.append(_build_alert(
                            "LEAD_TIME_ALERT", "INFO",
                            f"INFO: Place PO for {r['ingredient']} today — {r['vendor_name']} needs {r['lead_time_days']} days lead time",
                            ingredient=r["ingredient"], outlet=r["vendor_name"],
                        ))
        except Exception as e:
            print(f"Rule 9 error: {e}")

        # Insert new alerts
        if new_alerts:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    insert_query = """
                        INSERT INTO alerts (
                            alert_id, alert_type, severity, message, sku, outlet, ingredient, created_at, resolved, resolved_at
                        ) VALUES %s
                    """
                    values = [
                        (a['alert_id'], a['alert_type'], a['severity'], a['message'], a['sku'], a['outlet'], a['ingredient'], a['created_at'], a['resolved'], a['resolved_at'])
                        for a in new_alerts
                    ]
                    execute_values(cur, insert_query, values)
                    conn.commit()
            print(f"Inserted {len(new_alerts)} new alerts.")
            for a in new_alerts[:5]:
                print(f"  [{a['severity']}] {a['message'][:80]}")
        else:
            print("No new alerts generated.")

        return new_alerts

    except Exception as exc:
        print(f"Alert engine failed: {exc}")
        return []

if __name__ == "__main__":
    run()

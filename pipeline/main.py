"""
pipeline/main.py
─────────────────
Full pipeline orchestrator. Runs all steps in sequence:
  1. Extract from UrbanPiper + SupplyNote
  2. Clean + transform
  3. Load into local ClickHouse
  4. Run all 7 planning engines

Run with:
  python pipeline/main.py            (uses live connections)
  python pipeline/main.py --dummy    (uses dummy data)
"""

import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("pipeline.main")


# ── Import pipeline modules ───────────────────────────────────────────────────
from pipeline.extractors   import supplynote
from pipeline.transformers import clean
from pipeline.transformers import uom_converter
from pipeline.loaders import postgres as loader
from pipeline.loaders.postgres import log_pipeline_run
from pipeline.engines      import (
    forecast_engine,
    supply_planning,
    warehouse_planning,
    procurement_engine,
    alert_engine,
    variance_engine,
    cache_engine,
)


def run_full_pipeline(skip_extract: bool = False):
    """Execute the complete demand planning data pipeline."""
    started_at = datetime.now(IST)
    log.info("--------------------------------------------------------")
    log.info("    CUREFOODS DEMAND PLANNING PIPELINE - START          ")
    log.info("--------------------------------------------------------")
    log.info("Mode: LIVE DATA")
    if skip_extract:
        log.info("Extraction skipped. Processing existing database records.")
    log.info("Started at: %s", started_at.strftime("%Y-%m-%d %H:%M:%S %Z"))

    if not skip_extract:
        # ── STEP 1: EXTRACT ───────────────────────────────────────────────────────
        log.info("\n── STEP 1: EXTRACT ──────────────────────────────────────")

        log.info("Extracting from SupplyNote...")
        sn_data = supplynote.extract_all()

        # ── STEP 2: TRANSFORM / CLEAN ─────────────────────────────────────────────
        log.info("\n── STEP 2: CLEAN & TRANSFORM ────────────────────────────")

        kitchen_stock   = clean.clean_kitchen_stock(sn_data.get("kitchen_stock"))
        warehouse_stock = clean.clean_warehouse_stock(sn_data.get("warehouse_stock"))
        open_pos        = clean.clean_open_pos(sn_data.get("open_pos"))
        grn_log         = clean.clean_grn_log(sn_data.get("grn_log"))
        vendor_master   = clean.clean_vendor_master(sn_data.get("vendor_master"))

        # Convert UOM for stock tables
        for df in [kitchen_stock, warehouse_stock]:
            if not df.empty and "qty_available" in df.columns and "unit" in df.columns:
                uom_converter.convert_df_uom(df, "qty_available", "unit",
                                              ingredient_col="ingredient" if "ingredient" in df.columns else None)

        # ── STEP 3: LOAD ──────────────────────────────────────────────────────────
        log.info("\n── STEP 3: LOAD INTO CLICKHOUSE ─────────────────────────")

        client = loader.get_local_client()

        loader.insert_df(kitchen_stock,   "fact_kitchen_stock", client=client)
        loader.insert_df(warehouse_stock, "fact_warehouse_stock", client=client)
        loader.insert_df(open_pos,        "fact_open_pos",      client=client)
        loader.insert_df(grn_log,         "fact_grn_log",       client=client)
        loader.insert_df(vendor_master,   "dim_vendor_master",  client=client)

        client.close()

    # ── STEP 4 → 10: RUN PLANNING ENGINES ───────────────────────────────────
    log.info("\n── STEP 4-10: RUN PLANNING ENGINES ──────────────────────")

    log.info("\n[Engine 2] Forecast Engine (Prophet)")
    forecasts = forecast_engine.run()
    log_pipeline_run("forecast_engine", started_at, "SUCCESS", len(forecasts) if forecasts is not None else 0)

    log.info("\n[Engine 3] Supply Planning")
    supply_plan = supply_planning.run()
    # supply_planning logs itself

    log.info("\n[Engine 4] Variance Engine")
    variance_analysis = variance_engine.run_variance_engine()
    log_pipeline_run("variance_engine", started_at, "SUCCESS", len(variance_analysis) if variance_analysis is not None else 0)

    # Bypassed Engine 4: Recipe Explosion (we forecast ingredients directly now!)
    # Convert forecast directly into ingredient demand for warehouse planning
    if forecasts is not None and not forecasts.empty:
        # Group by both sku AND forecast_date
        ingredient_demand = forecasts.groupby(["forecast_date", "sku"], as_index=False)["qty_predicted"].sum()
        ingredient_demand = ingredient_demand.rename(columns={"sku": "ingredient", "qty_predicted": "total_qty_needed"})
        ingredient_demand["unit"] = "unit" # Dummy unit, can be mapped if needed
        ingredient_demand["outlet"] = "ALL"
        
        # Save to database so Procurement and Alert engines can use it
        from backend.database import get_db_connection
        import psycopg2
        from psycopg2.extras import execute_values
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS fact_ingredient_demand (
                        forecast_date DATE,
                        outlet VARCHAR(255),
                        ingredient VARCHAR(255),
                        unit VARCHAR(50),
                        total_qty_needed FLOAT
                    )
                ''')
                cur.execute("TRUNCATE TABLE fact_ingredient_demand")
                insert_query = '''
                    INSERT INTO fact_ingredient_demand (forecast_date, outlet, ingredient, unit, total_qty_needed)
                    VALUES %s
                '''
                values = [
                    (row['forecast_date'], row['outlet'], row['ingredient'], row['unit'], row['total_qty_needed'])
                    for _, row in ingredient_demand.iterrows()
                ]
                execute_values(cur, insert_query, values)
                conn.commit()
                log.info(f"Saved {len(values)} rows to fact_ingredient_demand")
                
        # For warehouse planning, we just need the aggregated sum per ingredient across all dates
        ingredient_demand_agg = ingredient_demand.groupby("ingredient", as_index=False)["total_qty_needed"].sum()
        ingredient_demand_agg["unit"] = "unit"
    else:
        ingredient_demand = None
        ingredient_demand_agg = pd.DataFrame(columns=["ingredient", "total_qty_needed", "unit"])


    log.info("\n[Engine 5] Warehouse Planning")
    warehouse_shortage = warehouse_planning.run(ingredient_demand=ingredient_demand_agg)
    log_pipeline_run("warehouse_planning", started_at, "SUCCESS", len(warehouse_shortage) if warehouse_shortage is not None else 0)

    log.info("\n[Engine 6] Procurement Engine")
    procurement_recs = procurement_engine.run()
    log_pipeline_run("procurement_engine", started_at, "SUCCESS", len(procurement_recs) if procurement_recs is not None else 0)

    log.info("\n[Engine 7] Alert Engine")
    new_alerts = alert_engine.run()
    log_pipeline_run("alert_engine", started_at, "SUCCESS", len(new_alerts) if new_alerts is not None else 0)

    log.info("\n[Engine 8] Cache Engine")
    cache_engine.run_cache_engine()

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now(IST) - started_at).total_seconds()
    log.info("\n--------------------------------------------------------")
    log.info("    PIPELINE COMPLETE - %.1fs                           ", elapsed)
    log.info("--------------------------------------------------------")
    log.info("Sales rows:          %d", 0) # Obsolete UrbanPiper engine removed
    log.info("Forecast rows:       %d", len(forecasts) if forecasts is not None else 0)
    log.info("Supply plan rows:    %d", len(supply_plan) if supply_plan is not None else 0)
    log.info("Ingredient demands:  %d", len(ingredient_demand_agg) if ingredient_demand is not None else 0)
    log.info("Shortage items:      %d", len(warehouse_shortage) if warehouse_shortage is not None else 0)
    log.info("Procurement recs:    %d", len(procurement_recs) if procurement_recs is not None else 0)
    log.info("New alerts:          %d", len(new_alerts))

    return {
        "forecasts":          forecasts,
        "supply_plan":        supply_plan,
        "ingredient_demand":  ingredient_demand,
        "warehouse_shortage": warehouse_shortage,
        "procurement_recs":   procurement_recs,
        "new_alerts":         new_alerts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Curefoods Demand Planning Pipeline")
    parser.add_argument("--dummy", action="store_true",
                        help="Use dummy data instead of live source connections")
    parser.add_argument("--process-only", action="store_true",
                        help="Skip extraction and process existing database records")
    args = parser.parse_args()

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    run_full_pipeline(skip_extract=args.process_only)

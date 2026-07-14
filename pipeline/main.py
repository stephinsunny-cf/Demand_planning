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
from pipeline.extractors   import urbanpiper, supplynote
from pipeline.transformers import clean
from pipeline.transformers import uom_converter
from pipeline.loaders      import postgres as loader
from pipeline.engines      import (
    sales_aggregation,
    forecast_engine,
    supply_planning,
    recipe_explosion,
    warehouse_planning,
    procurement_engine,
    alert_engine,
)


def run_full_pipeline(use_dummy: bool = False):
    """Execute the complete demand planning data pipeline."""
    started_at = datetime.now(IST)
    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║   CUREFOODS DEMAND PLANNING PIPELINE — START         ║")
    log.info("╚══════════════════════════════════════════════════════╝")
    log.info("Mode: %s", "DUMMY DATA" if use_dummy else "LIVE DATA")
    log.info("Started at: %s", started_at.strftime("%Y-%m-%d %H:%M:%S %Z"))

    # ── STEP 1: EXTRACT ───────────────────────────────────────────────────────
    log.info("\n── STEP 1: EXTRACT ──────────────────────────────────────")

    log.info("Extracting from UrbanPiper...")
    up_data = urbanpiper.extract_all(use_dummy=use_dummy)

    log.info("Extracting from SupplyNote...")
    sn_data = supplynote.extract_all(use_dummy=use_dummy)

    # ── STEP 2: TRANSFORM / CLEAN ─────────────────────────────────────────────
    log.info("\n── STEP 2: CLEAN & TRANSFORM ────────────────────────────")

    orders_clean = clean.clean_orders(up_data.get("orders"))
    items_clean  = clean.clean_order_items(up_data.get("order_items"))
    menu_clean   = clean.clean_menu_items(up_data.get("menu_items"))
    recipe_clean = clean.clean_recipe_master(up_data.get("recipe_master"))

    # Convert UOM on recipe master
    recipe_clean = uom_converter.convert_df_uom(
        recipe_clean, qty_col="qty_per_portion", unit_col="unit", ingredient_col="ingredient"
    )

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

    # Cross-table validation
    unmapped = clean.flag_unmapped_skus(items_clean, menu_clean)
    if unmapped:
        log.warning("Found %d unmapped SKUs — check menu_items", len(unmapped))

    # ── STEP 3: LOAD ──────────────────────────────────────────────────────────
    log.info("\n── STEP 3: LOAD INTO CLICKHOUSE ─────────────────────────")

    client = loader.get_local_client()

    loader.insert_df(orders_clean,    "fact_orders_raw",    client=client)
    loader.insert_df(items_clean,     "fact_order_items_raw", client=client)
    loader.insert_df(menu_clean,      "dim_menu_items",     client=client)
    loader.insert_df(recipe_clean,    "dim_recipe_master",  client=client)
    loader.insert_df(kitchen_stock,   "fact_kitchen_stock", client=client)
    loader.insert_df(warehouse_stock, "fact_warehouse_stock", client=client)
    loader.insert_df(open_pos,        "fact_open_pos",      client=client)
    loader.insert_df(grn_log,         "fact_grn_log",       client=client)
    loader.insert_df(vendor_master,   "dim_vendor_master",  client=client)

    client.close()

    # ── STEP 4 → 10: RUN PLANNING ENGINES ───────────────────────────────────
    log.info("\n── STEP 4-10: RUN PLANNING ENGINES ──────────────────────")

    log.info("\n[Engine 1] Sales Aggregation")
    daily_sales = sales_aggregation.run(orders_df=orders_clean, items_df=items_clean)

    log.info("\n[Engine 2] Forecast Engine (Prophet)")
    forecasts = forecast_engine.run()

    log.info("\n[Engine 3] Supply Planning")
    supply_plan = supply_planning.run()

    log.info("\n[Engine 4] Recipe Explosion")
    ingredient_demand = recipe_explosion.run()

    log.info("\n[Engine 5] Warehouse Planning")
    warehouse_shortage = warehouse_planning.run(ingredient_demand=ingredient_demand)

    log.info("\n[Engine 6] Procurement Engine")
    procurement_recs = procurement_engine.run()

    log.info("\n[Engine 7] Alert Engine")
    new_alerts = alert_engine.run()

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now(IST) - started_at).total_seconds()
    log.info("\n╔══════════════════════════════════════════════════════╗")
    log.info("║   PIPELINE COMPLETE — %.1fs                           ", elapsed)
    log.info("╚══════════════════════════════════════════════════════╝")
    log.info("Sales rows:          %d", len(daily_sales) if daily_sales is not None else 0)
    log.info("Forecast rows:       %d", len(forecasts) if forecasts is not None else 0)
    log.info("Supply plan rows:    %d", len(supply_plan) if supply_plan is not None else 0)
    log.info("Ingredient demands:  %d", len(ingredient_demand) if ingredient_demand is not None else 0)
    log.info("Shortage items:      %d", len(warehouse_shortage) if warehouse_shortage is not None else 0)
    log.info("Procurement recs:    %d", len(procurement_recs) if procurement_recs is not None else 0)
    log.info("New alerts:          %d", len(new_alerts))

    return {
        "daily_sales":        daily_sales,
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
    args = parser.parse_args()

    use_dummy = args.dummy or os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    run_full_pipeline(use_dummy=use_dummy)

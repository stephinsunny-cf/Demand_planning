"""
pipeline/scheduler.py
──────────────────────
Schedules all pipeline jobs at the correct frequencies using the `schedule` library.

Job schedule:
  - orders + order_items from UrbanPiper:  nightly at 2:00 AM
  - menu_items from UrbanPiper:            daily at 3:00 AM
  - recipe master from UrbanPiper:         daily at 3:30 AM
  - kitchen stock from SupplyNote:         every 4 hours
  - warehouse stock from SupplyNote:       every 4 hours
  - open POs from SupplyNote:              every 2 hours
  - GRN log from SupplyNote:               every 1 hour
  - vendor master from SupplyNote:         weekly on Sunday at 4:00 AM
  - full engines pipeline:                 daily at 4:00 AM (after all extracts)

Run with:
  python pipeline/scheduler.py
"""

import os
import sys
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import schedule

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("pipeline.scheduler")


def _safe_run(job_fn, job_name: str):
    """Wrap a job function with error handling so one failure doesn't stop the scheduler."""
    def wrapper():
        log.info("─" * 50)
        log.info("JOB START: %s @ %s", job_name, datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"))
        try:
            job_fn()
            log.info("JOB DONE:  %s", job_name)
        except Exception as exc:
            log.error("JOB FAILED: %s — %s", job_name, exc, exc_info=True)
    return wrapper


# ── Individual job functions ──────────────────────────────────────────────────

def job_urbanpiper_orders():
    """Pull orders and order_items from UrbanPiper (last 90 days)."""
    from pipeline.extractors import urbanpiper
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    data = urbanpiper.extract_all(use_dummy=use_dummy)
    orders_clean = clean.clean_orders(data.get("orders"))
    items_clean  = clean.clean_order_items(data.get("order_items"))
    loader.insert_df(orders_clean, "fact_orders_raw")
    loader.insert_df(items_clean, "fact_order_items_raw")


def job_urbanpiper_menu():
    """Pull menu_items from UrbanPiper (full table)."""
    from pipeline.extractors import urbanpiper
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    data = urbanpiper.extract_all(use_dummy=use_dummy)
    menu_clean = clean.clean_menu_items(data.get("menu_items"))
    loader.insert_df(menu_clean, "dim_menu_items")


def job_urbanpiper_recipes():
    """Pull dishes_ingredient_breakup (recipe master) from UrbanPiper."""
    from pipeline.extractors import urbanpiper
    from pipeline.transformers import clean, uom_converter
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    data = urbanpiper.extract_all(use_dummy=use_dummy)
    recipe_clean = clean.clean_recipe_master(data.get("recipe_master"))
    recipe_clean = uom_converter.convert_df_uom(recipe_clean, "qty_per_portion", "unit", "ingredient")
    loader.insert_df(recipe_clean, "recipe_master")


def job_supplynote_kitchen_stock():
    """Pull kitchen stock from SupplyNote (every 4 hours)."""
    from pipeline.extractors import supplynote
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    stock = supplynote.pull_kitchen_stock() if not use_dummy else supplynote._dummy_kitchen_stock()
    clean_stock = clean.clean_kitchen_stock(stock)
    loader.insert_df(clean_stock, "fact_kitchen_stock")


def job_supplynote_warehouse_stock():
    """Pull warehouse stock from SupplyNote (every 4 hours)."""
    from pipeline.extractors import supplynote
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    stock = supplynote.pull_warehouse_stock() if not use_dummy else supplynote._dummy_warehouse_stock()
    clean_stock = clean.clean_warehouse_stock(stock)
    loader.insert_df(clean_stock, "fact_warehouse_stock")


def job_supplynote_open_pos():
    """Pull open POs from SupplyNote (every 2 hours)."""
    from pipeline.extractors import supplynote
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    pos = supplynote.pull_open_pos() if not use_dummy else supplynote._dummy_open_pos()
    clean_pos = clean.clean_open_pos(pos)
    loader.insert_df(clean_pos, "fact_open_pos")


def job_supplynote_grn():
    """Pull GRN log from SupplyNote (every hour)."""
    from pipeline.extractors import supplynote
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    grn = supplynote.pull_grn_log() if not use_dummy else supplynote._dummy_grn_log()
    clean_grn = clean.clean_grn_log(grn)
    loader.insert_df(clean_grn, "fact_grn_log")


def job_supplynote_vendors():
    """Pull vendor master from SupplyNote (weekly)."""
    from pipeline.extractors import supplynote
    from pipeline.transformers import clean
    from pipeline.loaders import clickhouse as loader

    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    vendors = supplynote.pull_vendor_master() if not use_dummy else supplynote._dummy_vendor_master()
    clean_vendors = clean.clean_vendor_master(vendors)
    loader.insert_df(clean_vendors, "dim_vendor_master")


def job_run_all_engines():
    """Run all 7 planning engines in sequence."""
    from pipeline.engines import (
        sales_aggregation,
        forecast_engine,
        supply_planning,
        recipe_explosion,
        warehouse_planning,
        procurement_engine,
        alert_engine,
    )
    daily_sales       = sales_aggregation.run()
    forecasts         = forecast_engine.run()
    supply_plan       = supply_planning.run()
    ingredient_demand = recipe_explosion.run(supply_plan=supply_plan)
    shortage          = warehouse_planning.run(ingredient_demand=ingredient_demand)
    procurement_engine.run(warehouse_shortage=shortage)
    alert_engine.run()


# ── Schedule all jobs ─────────────────────────────────────────────────────────

def setup_schedule():
    # UrbanPiper pulls
    schedule.every().day.at("02:00").do(_safe_run(job_urbanpiper_orders,   "urbanpiper_orders"))
    schedule.every().day.at("03:00").do(_safe_run(job_urbanpiper_menu,     "urbanpiper_menu"))
    schedule.every().day.at("03:30").do(_safe_run(job_urbanpiper_recipes,  "urbanpiper_recipes"))

    # SupplyNote pulls
    schedule.every(4).hours.do(_safe_run(job_supplynote_kitchen_stock,   "supplynote_kitchen_stock"))
    schedule.every(4).hours.do(_safe_run(job_supplynote_warehouse_stock, "supplynote_warehouse_stock"))
    schedule.every(2).hours.do(_safe_run(job_supplynote_open_pos,        "supplynote_open_pos"))
    schedule.every(1).hours.do(_safe_run(job_supplynote_grn,             "supplynote_grn"))
    schedule.every().sunday.at("04:00").do(_safe_run(job_supplynote_vendors, "supplynote_vendors"))

    # All planning engines (after all data is loaded)
    schedule.every().day.at("04:00").do(_safe_run(job_run_all_engines, "all_engines"))

    log.info("Scheduler configured with %d jobs:", len(schedule.jobs))
    for job in schedule.jobs:
        log.info("  %s", job)


def main():
    log.info("Starting Demand Planning Scheduler...")
    setup_schedule()

    # Run engines once immediately on startup
    log.info("Running initial pipeline on startup...")
    use_dummy = os.getenv("USE_DUMMY_DATA", "false").lower() == "true"
    try:
        from pipeline.main import run_full_pipeline
        run_full_pipeline(use_dummy=use_dummy)
    except Exception as exc:
        log.error("Initial pipeline run failed: %s", exc)

    log.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds


if __name__ == "__main__":
    main()

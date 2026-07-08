"""
pipeline/create_tables.py
─────────────────────────
Creates all ClickHouse tables in the local demand_planning database.
Run this ONCE before running the pipeline for the first time.
It is fully idempotent — safe to run multiple times.
"""

import os
import sys
import logging
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def get_client():
    return clickhouse_connect.get_client(
        host=os.getenv("LOCAL_HOST", "localhost"),
        port=int(os.getenv("LOCAL_PORT", 8123)),
        username=os.getenv("LOCAL_USER", "default"),
        password=os.getenv("LOCAL_PASSWORD", "admin123"),
        database="default",
    )


DDL_STATEMENTS = [
    # ── Database ──────────────────────────────────────────────────────
    "CREATE DATABASE IF NOT EXISTS demand_planning",

    # ── Fact Tables ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_daily_sales (
        date            Date,
        sku             String,
        brand           String,
        outlet          String,
        city            String,
        qty_sold        Float32,
        revenue         Float32,
        order_count     UInt32,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (date, sku, outlet)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_kitchen_stock (
        snapshot_time   DateTime,
        kitchen         String,
        ingredient      String,
        qty_available   Float32,
        unit            String,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (snapshot_time, kitchen, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_warehouse_stock (
        snapshot_time   DateTime,
        warehouse       String,
        ingredient      String,
        qty_available   Float32,
        unit            String,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (snapshot_time, warehouse, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_open_pos (
        po_number       String,
        vendor          String,
        ingredient      String,
        qty_ordered     Float32,
        expected_date   Date,
        status          String,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (po_number, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_grn_log (
        grn_number      String,
        po_number       String,
        ingredient      String,
        qty_ordered     Float32,
        qty_received    Float32,
        received_date   Date,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (received_date, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_forecast (
        forecast_date   Date,
        sku             String,
        outlet          String,
        qty_predicted   Float32,
        qty_lower       Float32,
        qty_upper       Float32,
        model_run_date  Date
    ) ENGINE = MergeTree()
    ORDER BY (forecast_date, sku, outlet)
    """,

    # ── Dimension Tables (ReplacingMergeTree for upserts) ─────────────
    """
    CREATE TABLE IF NOT EXISTS dim_menu_items (
        id              String,
        name            String,
        brand           String,
        category        String,
        price           Float32,
        active          UInt8,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(inserted_at)
    ORDER BY (id)
    """,

    """
    CREATE TABLE IF NOT EXISTS dim_recipe_master (
        dish_name       String,
        ingredient      String,
        qty_per_portion Float32,
        unit            String,
        yield_factor    Float32 DEFAULT 1.0,
        updated_at      DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY (dish_name, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS dim_vendor_master (
        vendor_name     String,
        ingredient      String,
        lead_time_days  UInt8,
        moq             Float32,
        unit            String,
        price           Float32,
        updated_at      DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY (vendor_name, ingredient)
    """,

    """
    CREATE TABLE IF NOT EXISTS dim_safety_stock (
        sku                 String,
        outlet              String,
        safety_stock_days   Float32 DEFAULT 2.0,
        safety_stock_qty    Float32,
        updated_at          DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY (sku, outlet)
    """,

    # ── Alerts ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS alerts (
        alert_id    String DEFAULT generateUUIDv4(),
        alert_type  String,
        severity    String,
        message     String,
        sku         String,
        outlet      String,
        ingredient  String,
        created_at  DateTime DEFAULT now(),
        resolved    UInt8 DEFAULT 0,
        resolved_at DateTime
    ) ENGINE = MergeTree()
    ORDER BY (created_at, severity)
    """,

    # ── Raw staging tables (for debug) ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_orders_raw (
        order_id        String,
        created_at      DateTime,
        store_name      String,
        brand           String,
        status          String,
        total           Float32,
        city            String,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (created_at, store_name)
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_order_items_raw (
        id              String,
        order_id        String,
        item_name       String,
        quantity        Float32,
        price           Float32,
        created_at      DateTime,
        inserted_at     DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (created_at, item_name)
    """,

    # ── Pipeline metadata ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id          String DEFAULT generateUUIDv4(),
        job_name        String,
        started_at      DateTime DEFAULT now(),
        completed_at    DateTime,
        status          String,
        rows_processed  UInt32,
        error_message   String
    ) ENGINE = MergeTree()
    ORDER BY (started_at, job_name)
    """,
]


def create_all_tables():
    log.info("Connecting to local ClickHouse at %s:%s",
             os.getenv("LOCAL_HOST", "localhost"),
             os.getenv("LOCAL_PORT", 8123))
    try:
        client = get_client()
        log.info("Connected successfully.")
    except Exception as exc:
        log.error("Cannot connect to local ClickHouse: %s", exc)
        log.error("Make sure Docker is running: docker start clickhouse-local")
        sys.exit(1)

    success = 0
    errors = 0
    for stmt in DDL_STATEMENTS:
        stmt_preview = stmt.strip()[:60].replace("\n", " ")
        try:
            client.command(stmt)
            log.info("OK  %s...", stmt_preview)
            success += 1
        except Exception as exc:
            log.error("FAIL %s... → %s", stmt_preview, exc)
            errors += 1

    log.info("─" * 60)
    log.info("Tables created: %d  |  Errors: %d", success, errors)

    # Verify by listing tables
    log.info("Verifying tables in demand_planning database:")
    try:
        result = client.query("SHOW TABLES FROM demand_planning")
        tables = [row[0] for row in result.result_rows]
        for t in sorted(tables):
            log.info("  ✓ %s", t)
    except Exception as exc:
        log.warning("Could not list tables: %s", exc)

    client.close()
    log.info("Done. Run 'python pipeline/main.py' to start the pipeline.")


if __name__ == "__main__":
    create_all_tables()

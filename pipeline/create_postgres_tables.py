"""
pipeline/create_postgres_tables.py
───────────────────────────────────
Creates all required pipeline staging and output tables in PostgreSQL.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import get_db_connection

DDL_STATEMENTS = [
    # ── Fact Tables (Raw) ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_orders_raw (
        order_id        VARCHAR(100) PRIMARY KEY,
        created_at      TIMESTAMP,
        store_name      VARCHAR(100),
        brand           VARCHAR(100),
        status          VARCHAR(50),
        total           REAL,
        city            VARCHAR(100),
        inserted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_order_items_raw (
        id              VARCHAR(100) PRIMARY KEY,
        order_id        VARCHAR(100),
        item_name       VARCHAR(255),
        quantity        REAL,
        price           REAL,
        inserted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_open_pos (
        po_number       VARCHAR(100),
        vendor          VARCHAR(100),
        ingredient      VARCHAR(100),
        qty_ordered     REAL,
        expected_date   DATE,
        status          VARCHAR(50),
        inserted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (po_number, ingredient)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_grn_log (
        grn_number      VARCHAR(100),
        po_number       VARCHAR(100),
        received_date   DATE,
        vendor          VARCHAR(100),
        ingredient      VARCHAR(100),
        qty_received    REAL,
        inserted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Dimension Tables ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_menu_items (
        sku             VARCHAR(100) PRIMARY KEY,
        item_name       VARCHAR(255),
        brand           VARCHAR(100),
        category        VARCHAR(100),
        price           REAL,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_vendor_master (
        vendor_id       VARCHAR(100) PRIMARY KEY,
        vendor_name     VARCHAR(255),
        category        VARCHAR(100),
        rating          REAL,
        lead_time_days  INT,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS custom_events (
        id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        event_name      VARCHAR(255),
        event_date      DATE,
        outlet          VARCHAR(100)
    )
    """,
    
    # ── Pipeline Output Tables (Supply Plan) ───────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS fact_supply_plan (
        plan_date       DATE,
        sku             VARCHAR(100),
        outlet          VARCHAR(100),
        qty_to_produce  REAL,
        safety_stock    REAL,
        run_date        DATE,
        inserted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
]

def main():
    print("Connecting to PostgreSQL to create missing tables...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for sql in DDL_STATEMENTS:
                print(f"Executing: {sql.strip().splitlines()[0][:50]}...")
                cur.execute(sql)
            conn.commit()
        print("All tables created successfully!")
    except Exception as e:
        print(f"Error creating tables: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()

import sys
import os
from pathlib import Path

# Add project root to sys.path so backend imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import get_db_connection

INDEX_STATEMENTS = [
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_orders_created_at ON pos_orders (created_at_ist);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_orders_brand ON pos_orders (brand_name);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_items_order_id ON pos_order_items (order_id);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_items_item_name ON pos_order_items (item_name);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_forecast_date ON fact_forecast (forecast_date);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_forecast_outlet ON fact_forecast (outlet);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_warehouse_snapshot ON fact_warehouse_stock (snapshot_time);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_warehouse_ingredient ON fact_warehouse_stock (ingredient);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_ingredient_demand_idx ON fact_ingredient_demand (forecast_date, outlet, ingredient);",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_kitchen_stock_idx ON fact_kitchen_stock (kitchen, ingredient, snapshot_date);"
]

def main():
    print("Applying performance indexes to PostgreSQL...")
    conn = get_db_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for sql in INDEX_STATEMENTS:
                print(f"Executing: {sql}")
                cur.execute(sql)
        print("✅ All indexes applied successfully!")
    except Exception as e:
        print(f"❌ Error creating indexes: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()

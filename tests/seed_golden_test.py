import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(r'd:\demand-planning\.env')
pg_url = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"
engine = create_engine(pg_url)

with engine.begin() as conn:
    # 1. Insert POS Order
    conn.execute(text("""
        INSERT INTO pos_orders (id, store_name, created_at_ist)
        VALUES ('test_order_9999', 'Khichdi Tales Jlt', '2026-07-16 12:00:00')
        ON CONFLICT (id) DO NOTHING;
    """))
    
    # 2. Insert POS Order Item (1 Palak Paneer Khichdi -> Expected 101g CFIDG232)
    conn.execute(text("""
        INSERT INTO pos_order_items (id, order_id, item_name, quantity, option_names)
        VALUES ('test_item_9999', 'test_order_9999', 'Palak Paneer Khichdi', 1, NULL)
        ON CONFLICT (id) DO NOTHING;
    """))

    # 3. Insert SupplyNote Actual Consumption (Actual 90g CFIDG232)
    conn.execute(text("""
        INSERT INTO fact_daily_sales (date, outlet, sku, qty_sold, revenue)
        VALUES ('2026-07-16', 'Khichdi Tales Jlt', 'CFIDG232', 90.0, 0.0)
    """))

print("Successfully inserted deliberate test case: Expected=101, Actual=90 for 2026-07-16")

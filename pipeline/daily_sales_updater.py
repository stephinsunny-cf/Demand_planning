import os
import sys
import pandas as pd
from datetime import datetime, timezone, timedelta
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.extractors.urbanpiper import extract_all
from pipeline.transformers.clean import clean_orders, clean_order_items

load_dotenv()
IST = timezone(timedelta(hours=5, minutes=30))

PG_HOST = "103.172.150.31"
PG_USER = "new_user"
PG_PASS = "StrongPassword123!"
PG_DB = "demand_planning"
PG_PORT = 5432

def run_daily_sales_update():
    print(f"[{datetime.now(IST)}] Running Daily Sales Extractor...")
    
    # 1. Extract from UrbanPiper (last 5 days by default due to fallback/dummy or config in extract_all, 
    # but since it's dummy data if connection fails, it gives 90 days. We'll let it pull everything and we UPSERT)
    up_data = extract_all(use_dummy=False)
    
    orders = clean_orders(up_data.get("orders"))
    items = clean_order_items(up_data.get("order_items"))
    
    if orders.empty or items.empty:
        print("No order data found to update.")
        return
        
    print(f"Pulled {len(orders)} orders and {len(items)} items. Joining...")
    
    # 2. Transform (similar to sales_transformer.py)
    df = pd.merge(orders, items, left_on='order_id', right_on='order_id', how='inner')
    
    df['date'] = pd.to_datetime(df['created_at_x']).dt.date
    df['total'] = pd.to_numeric(df['total'].astype(str).str.replace(',', ''), errors='coerce').fillna(0.0)
    df['quantity'] = pd.to_numeric(df['quantity'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    print("Aggregating sales by date, SKU, and outlet...")
    agg = df.groupby(['date', 'item_name', 'store_name'], dropna=False).agg(
        qty_sold=('quantity', 'sum'),
        revenue=('total', 'sum'),
        order_count=('order_id', 'nunique'),
        brand=('brand', 'first'),
        city=('city', 'first')
    ).reset_index()
    
    agg = agg.rename(columns={
        'item_name': 'sku',
        'store_name': 'outlet'
    })
    agg = agg.where(pd.notnull(agg), None)
    
    # 3. Upsert into Postgres
    print(f"Upserting {len(agg)} aggregated sales records to Postgres...")
    conn = psycopg2.connect(host=PG_HOST, user=PG_USER, password=PG_PASS, dbname=PG_DB, port=PG_PORT)
    try:
        with conn.cursor() as cursor:
            insert_query = """
                INSERT INTO fact_daily_sales (date, sku, brand, outlet, city, qty_sold, revenue, order_count)
                VALUES %s
                ON CONFLICT (date, sku, outlet) 
                DO UPDATE SET 
                    qty_sold = EXCLUDED.qty_sold,
                    revenue = EXCLUDED.revenue,
                    order_count = EXCLUDED.order_count;
            """
            
            # Create tuples for execute_values
            # Filter out rows where sku or outlet is None (primary key cannot be null)
            agg = agg.dropna(subset=['date', 'sku', 'outlet'])
            
            values = [
                (row['date'], row['sku'], row['brand'], row['outlet'], row['city'], 
                 int(row['qty_sold']), float(row['revenue']), int(row['order_count']))
                for _, row in agg.iterrows()
            ]
            
            execute_values(cursor, insert_query, values)
            conn.commit()
            print(f"Successfully upserted {len(values)} sales records to fact_daily_sales!")
            
    except Exception as e:
        print(f"Database upsert failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_daily_sales_update()

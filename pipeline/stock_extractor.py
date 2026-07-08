import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine
import pandas as pd

load_dotenv()

SUPPLYNOTE_USER = os.getenv("SUPPLYNOTE_USER")
SUPPLYNOTE_PASSWORD = os.getenv("SUPPLYNOTE_PASSWORD")

PG_HOST = "103.172.150.31"
PG_USER = "new_user"
PG_PASS = "StrongPassword123!"
PG_DB = "demand_planning"
PG_PORT = 5432
PG_URI = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

def get_live_cookies():
    print("Logging into SupplyNote...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto("https://www.supplynote.in/signin")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[placeholder="Enter your username"]', SUPPLYNOTE_USER)
        page.fill('input[placeholder="Enter your password"]', SUPPLYNOTE_PASSWORD)
        page.click('button:has-text("LOG IN")')
        page.wait_for_load_state("networkidle")
        
        business_id = page.evaluate("localStorage.getItem('business')")
        if business_id:
            business_id = business_id.replace('"', '')
        else:
            business_id = '65b205675255c93a41dd7849'
            
        cookies = context.cookies()
        browser.close()
        return cookies, business_id

from psycopg2.extras import execute_values

def insert_into_postgres(engine, stock_data):
    if not stock_data:
        return
    
    print(f"Upserting {len(stock_data)} stock records into Postgres...")
    
    # We use psycopg2 directly for UPSERT
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cursor:
            insert_query = """
                INSERT INTO fact_kitchen_stock (snapshot_date, kitchen, ingredient, qty_available, unit)
                VALUES %s
                ON CONFLICT (snapshot_date, kitchen, ingredient) 
                DO UPDATE SET 
                    qty_available = EXCLUDED.qty_available,
                    unit = EXCLUDED.unit;
            """
            raw_values = [
                (d['snapshot_date'].date(), d['kitchen'], d['ingredient'], d['qty_available'], d['unit']) 
                for d in stock_data
            ]
            
            # Deduplicate before insertion to avoid ON CONFLICT errors within the same batch
            unique_values = {}
            for row in raw_values:
                key = (row[0], row[1], row[2]) # (snapshot_date, kitchen, ingredient)
                unique_values[key] = row
            values = list(unique_values.values())
            
            execute_values(cursor, insert_query, values)
            conn.commit()
    except Exception as e:
        print(f"Failed to upsert: {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    cookies, business_id = get_live_cookies()
    print(f"Business ID: {business_id}")
    
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.supplynote.in',
        'User-Agent': 'Mozilla/5.0'
    }
    session.headers.update(headers)
    
    print("Fetching outlets...")
    outlets_url = f"https://www.supplynote.in/api/outlets?buisness={business_id}"
    res = session.get(outlets_url)
    if res.status_code != 200:
        print("Failed to get outlets")
        return
        
    outlets_data = res.json()
    if isinstance(outlets_data, list):
        outlets = outlets_data
    else:
        outlets = outlets_data.get("data", [])
        
    if not outlets:
        print("No outlets found")
        return
        
    engine = create_engine(PG_URI)
    snapshot_time = datetime.now()
    
    all_stock_records = []
    
    # For demonstration, limit to a few outlets to avoid making 300+ API calls synchronously in testing
    # In a real background job, we would remove this slice.
    print(f"Found {len(outlets)} outlets. Fetching stock for all...")
    
    for outlet in outlets:
        outlet_name = outlet.get('outletName', outlet.get('name', 'Unknown'))
        outlet_id = outlet.get('id', outlet.get('_id'))
        if not outlet_id:
            continue
            
        stock_url = f"https://www.supplynote.in/api/outletproducts/outlet/{outlet_id}?capex=false&parentProducts=false"
        res2 = session.get(stock_url)
        if res2.status_code != 200:
            print(f"Failed to get stock for outlet {outlet_name}")
            continue
            
        stock_data = res2.json()
        
        for item in stock_data:
            prod = item.get('product', {})
            name = prod.get('productTitle', 'Unknown')
            qty = item.get('currentStock', 0)
            unit = prod.get('baseUnit', 'Unknown')
            
            all_stock_records.append({
                'snapshot_date': snapshot_time,
                'kitchen': outlet_name,
                'ingredient': name,
                'qty_available': float(qty),
                'unit': unit
            })
            
    insert_into_postgres(engine, all_stock_records)
    print("Stock extraction complete!")

if __name__ == '__main__':
    main()

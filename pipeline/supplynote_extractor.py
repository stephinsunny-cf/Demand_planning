import os
import time
import datetime
import io
import pandas as pd
import requests
from sqlalchemy import create_engine
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

SUPPLYNOTE_USER = os.getenv("SUPPLYNOTE_USER")
SUPPLYNOTE_PASSWORD = os.getenv("SUPPLYNOTE_PASSWORD")

# Postgres connection string
PG_HOST = "103.172.150.31"
PG_USER = "new_user"
PG_PASS = "StrongPassword123!"
PG_DB = "demand_planning"
PG_PORT = 5432
PG_URI = f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

def get_live_cookies():
    print("Launching invisible browser to log into SupplyNote...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate to actual signin page
        print("Navigating to signin page...")
        page.goto("https://www.supplynote.in/signin")
        page.wait_for_load_state("networkidle")
        
        print("Entering credentials...")
        page.fill('input[placeholder="Enter your username"]', SUPPLYNOTE_USER)
        page.fill('input[placeholder="Enter your password"]', SUPPLYNOTE_PASSWORD)
        
        print("Clicking login...")
        page.click('button:has-text("LOG IN")')
        
        # Wait for dashboard/recipes to load
        print("Waiting for login to complete...")
        page.wait_for_load_state("networkidle")
        
        # We need the business ID from localStorage or from a URL
        business_id = page.evaluate("localStorage.getItem('business')")
        if not business_id:
            business_id = '65b205675255c93a41dd7849' # Fallback
            print("Could not find business ID in localStorage, using fallback.")
        else:
            business_id = business_id.replace('"', '')
            
        print(f"Logged in successfully! Business ID: {business_id}")
        
        # Extract cookies
        cookies = context.cookies()
        browser.close()
        
        return cookies, business_id

def truncate_postgres(engine):
    print("Wiping existing data from Postgres...")
    with engine.begin() as conn:
        conn.execute("TRUNCATE TABLE fact_forecast")
        conn.execute("TRUNCATE TABLE fact_daily_sales")
    print("Postgres tables wiped successfully.")

def insert_into_postgres(engine, df):
    # Prepare forecast data
    df_fcst = pd.DataFrame()
    df_fcst['forecast_date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
    df_fcst['sku'] = df['ingredientName'].astype(str)
    df_fcst['outlet'] = df['kitchenName'].astype(str)
    df_fcst['qty_predicted'] = df['plannedDemand'].fillna(0.0).astype(float)
    df_fcst['qty_lower'] = df_fcst['qty_predicted'] * 0.9
    df_fcst['qty_upper'] = df_fcst['qty_predicted'] * 1.1
    df_fcst['model_run_date'] = datetime.date.today()
    df_fcst['model_name'] = 'SupplyNote'
    df_fcst['mape_7d'] = 0.0
    
    df_fcst.dropna(subset=['sku', 'outlet'], inplace=True)
    
    # Prepare sales data
    df_sales = pd.DataFrame()
    df_sales['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
    df_sales['sku'] = df['ingredientName'].astype(str)
    df_sales['brand'] = 'SupplyNote'
    df_sales['outlet'] = df['kitchenName'].astype(str)
    df_sales['city'] = df.get('city', 'Unknown').astype(str)
    df_sales['qty_sold'] = df['sold'].fillna(0.0).abs().astype(int)
    df_sales['revenue'] = 0.0
    df_sales['order_count'] = 0
    
    df_sales.dropna(subset=['sku', 'outlet'], inplace=True)
    
    if not df_fcst.empty or not df_sales.empty:
        print(f"Inserting {len(df_fcst)} rows into Postgres...")
        if not df_fcst.empty:
            df_fcst.to_sql('fact_forecast', engine, if_exists='append', index=False)
        if not df_sales.empty:
            df_sales.to_sql('fact_daily_sales', engine, if_exists='append', index=False)
        print("Insertion complete.")

def main():
    print("--- Starting Automated SupplyNote Extraction Pipeline ---")
    
    if not SUPPLYNOTE_USER or not SUPPLYNOTE_PASSWORD:
        print("ERROR: SUPPLYNOTE_USER and SUPPLYNOTE_PASSWORD are not set in .env file!")
        return

    try:
        raw_cookies, business_id = get_live_cookies()
    except Exception as e:
        print(f"Login failed: {e}")
        print("Please check your credentials or if SupplyNote has changed their login page.")
        return
        
    # Format cookies for requests
    session = requests.Session()
    for cookie in raw_cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.supplynote.in',
        'Referer': 'https://www.supplynote.in/demandplans/history',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    session.headers.update(headers)

    engine = create_engine(PG_URI)
    truncate_postgres(engine)
    
    today = datetime.date.today()
    dates_to_fetch = [today - datetime.timedelta(days=i) for i in range(180)]
    total_downloaded = 0
    
    for target_date in dates_to_fetch:
        prev_day = target_date - datetime.timedelta(days=1)
        plan_date_str = f"{prev_day.strftime('%Y-%m-%d')}T18:30:00.000Z"
        
        history_url = f"https://www.supplynote.in/api/demandplan/history/semiFinished?business={business_id}&planDate={plan_date_str}"
        print(f"\nFetching {target_date.strftime('%Y-%m-%d')}...")
        
        try:
            res = session.get(history_url, timeout=10)
        except Exception as e:
            print(f"Request timeout/error: {e}")
            continue
            
        if res.status_code != 200:
            print(f"Error {res.status_code}: API rejected the request.")
            continue
            
        data = res.json()
        if not data.get('data') or len(data['data']) == 0:
            print("No uploads found for this date.")
            continue
            
        version_key = data['data'][0].get('versionKey')
        dl_url = f"https://www.supplynote.in/api/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}"
        
        try:
            print(f"Requesting download link for {version_key}...")
            res2 = session.get(dl_url, timeout=60)
        except Exception as e:
            print(f"Download API error: {e}")
            continue
            
        if res2.status_code == 200:
            s3_link = res2.json().get('data')
            if s3_link:
                try:
                    # Use stream=True to prevent MemoryError on massive CSVs
                    csv_res = requests.get(s3_link, timeout=20, stream=True)
                    if csv_res.status_code != 200:
                        print(f"S3 Error Status: {csv_res.status_code}")
                        continue
                        
                    # stream the response content into pd.read_csv in chunks to avoid OOM
                    csv_res.raw.decode_content = True
                    chunk_iter = pd.read_csv(csv_res.raw, chunksize=50000, low_memory=False)
                    for chunk in chunk_iter:
                        if not chunk.empty:
                            insert_into_postgres(engine, chunk)
                            total_downloaded += len(chunk)
                except Exception as e:
                    import traceback
                    print(f"Failed to read CSV from S3: {e}")
                    traceback.print_exc()
            else:
                print("No S3 link returned.")
        else:
            print(f"Failed to get S3 link. Status: {res2.status_code}")
            
        time.sleep(1)
        
    print(f"\n--- Pipeline Complete! Total Rows Extracted: {total_downloaded} ---")

if __name__ == "__main__":
    main()

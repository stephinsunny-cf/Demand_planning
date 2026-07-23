"""
SupplyNote - All Ingredient Data Importer
Uses the correct API: /api/demandplan/download/semiFinished-combined?type=all&versionKey=...
Downloads the full 460k rows/day "All Ingredient Data" CSV for Jan–Jul 2026.
"""
import os
import re
import io
import logging
import requests
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s")
log = logging.getLogger("supplynote_importer")

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

SN_USERNAME = os.getenv("SUPPLYNOTE_USER") or os.getenv("SN_USERNAME", "")
SN_PASSWORD = os.getenv("SUPPLYNOTE_PASSWORD") or os.getenv("SN_PASS", "")
BUSINESS_ID = "65b205675255c93a41dd7849"

BASE = "https://www.supplynote.in/api"
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
IST = timezone(timedelta(hours=5, minutes=30))


def _find_jwt_in(data) -> str | None:
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, str) and JWT_RE.match(v):
                return v
            found = _find_jwt_in(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_jwt_in(item)
            if found:
                return found
    return None


def login() -> str:
    for url in ["https://www.supplynote.in/api/auth/signin", "https://www.supplynote.in/api/auth/login"]:
        for body in [{"username": SN_USERNAME, "password": SN_PASSWORD}, {"email": SN_USERNAME, "password": SN_PASSWORD}]:
            try:
                res = requests.post(url, json=body, timeout=20)
                if res.status_code == 404:
                    break
                if res.status_code in (200, 201):
                    token = _find_jwt_in(res.json())
                    if token:
                        log.info("Login successful — JWT obtained.")
                        return token
                    m = JWT_RE.search(res.text)
                    if m:
                        return m.group(0)
            except Exception as e:
                log.warning(f"Login error: {e}")
    raise RuntimeError("Could not login to SupplyNote.")


def date_to_plan_date(d: date) -> str:
    midnight_ist = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    return midnight_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_version_key(token: str, target_date: date) -> str | None:
    """Get the latest versionKey for a given date from semiFinished history."""
    plan_date = date_to_plan_date(target_date)
    url = f"{BASE}/demandplan/history/semiFinished?business={BUSINESS_ID}&planDate={requests.utils.quote(plan_date)}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    res = requests.get(url, headers=headers, timeout=30)
    if not res.ok:
        return None
    versions = res.json()
    versions = versions if isinstance(versions, list) else versions.get("data", [])
    if not versions:
        return None
    return versions[0].get("versionKey")


def get_download_url(session: requests.Session, token: str, version_key: str) -> str | None:
    """Call the All Ingredient Data endpoint to get the S3 download URL."""
    url = f"{BASE}/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.supplynote.in/demandplans/history",
        "Origin": "https://www.supplynote.in",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    import time
    for attempt in range(5):
        try:
            log.info(f"  Requesting download URL (attempt {attempt+1}/5) for version {version_key}...")
            res = session.get(url, headers=headers, timeout=120)
            
            if res.status_code == 504:
                log.warning(f"  HTTP 504 Gateway Timeout. The server is still building the file in the background. Waiting 30s before checking if it's done...")
                time.sleep(30)
                continue
                
            if not res.ok:
                log.warning(f"  Download URL fetch failed: HTTP {res.status_code} - {res.text[:100]}")
                return None
                
            data = res.json()
            return data.get("data")
            
        except requests.exceptions.ReadTimeout:
            log.warning(f"  ReadTimeout. The server is building the file. Waiting 30s before retrying...")
            time.sleep(30)
            
    return None




def download_csv(s3_url: str) -> pd.DataFrame | None:
    """Download and parse the CSV from S3. These are large files so use 180s timeout."""
    for attempt in range(3):
        try:
            res = requests.get(s3_url, timeout=180)
            if not res.ok:
                return None
            content = res.content.decode("utf-8-sig", errors="replace")
            df = pd.read_csv(io.StringIO(content))
            return df
        except requests.exceptions.ReadTimeout:
            log.warning(f"  Timeout downloading CSV (attempt {attempt+1}/3), retrying...")
            import time; time.sleep(5)
        except Exception as e:
            log.warning(f"CSV download/parse error: {e}")
            return None
    return None


def run():
    session = requests.Session()  # Reuse session for all requests
    token = login()
    # Set browser-like headers on session for all future requests
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.supplynote.in/demandplans/history",
        "Origin": "https://www.supplynote.in",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    start_date = date(2026, 1, 1)
    end_date   = datetime.now().date()

    all_records = []
    seen_version_keys = set()  # Avoid downloading same version twice

    curr_date = end_date
    log.info(f"Fetching ALL INGREDIENT DATA backwards from {end_date} down to {start_date} ...")

    while curr_date >= start_date:
        version_key = get_version_key(token, curr_date)
        if not version_key:
            curr_date -= timedelta(days=1)
            continue

        # Skip if we already downloaded this version (same upload covers multiple dates)
        if version_key in seen_version_keys:
            log.info(f"  {curr_date}: version {version_key} already downloaded, skipping.")
            curr_date -= timedelta(days=1)
            continue

        seen_version_keys.add(version_key)

        s3_url = get_download_url(session, token, version_key)
        if not s3_url:
            log.warning(f"  {curr_date}: Could not get S3 URL for version {version_key}")
            curr_date -= timedelta(days=1)
            continue

        df = download_csv(s3_url)
        if df is None or df.empty:
            log.warning(f"  {curr_date}: Empty or failed CSV for version {version_key}")
            curr_date -= timedelta(days=1)
            continue
            
        # Save raw CSV to project folder
        try:
            download_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supplynote_downloads")
            os.makedirs(download_dir, exist_ok=True)
            csv_path = os.path.join(download_dir, f"supplynote_{curr_date}.csv")
            df.to_csv(csv_path, index=False)
            log.info(f"  Saved raw CSV to {csv_path}")
        except Exception as e:
            log.warning(f"  Failed to save raw CSV to folder: {e}")

        # Map columns — we know from inspection the CSV has these columns:
        # versionKey, date, kitchenId, kitchenCode, city, kitchenName,
        # ingredientId, ingredientCode, ingredientName, ingredientCategory,
        # isPackaged, measuringUnit, plannedDemand, rolloverDemand, currentlyAvailable, sold, oos

        if 'ingredientCode' not in df.columns or 'kitchenCode' not in df.columns:
            log.warning(f"  {curr_date}: Missing ingredientCode/kitchenCode. Columns: {list(df.columns)}")
            curr_date -= timedelta(days=1)
            continue

        if 'ingredientName' not in df.columns or 'plannedDemand' not in df.columns:
            log.warning(f"  {curr_date}: Unexpected columns: {list(df.columns)}")
            curr_date -= timedelta(days=1)
            continue

        df['date_parsed'] = pd.to_datetime(df.get('date', str(curr_date)), format='%d-%m-%Y', errors='coerce').fillna(curr_date)
        df['qty_sold'] = pd.to_numeric(df['plannedDemand'], errors='coerce').fillna(0)

        # Keep the code alongside the name for reliable deduplication
        records = df[['date_parsed', 'ingredientCode', 'ingredientName', 'kitchenCode', 'kitchenName', 'qty_sold']].copy()
        
        # Strip whitespace from codes/names
        records['ingredientCode'] = records['ingredientCode'].str.strip()
        records['ingredientName'] = records['ingredientName'].str.strip()
        records['kitchenCode']    = records['kitchenCode'].str.strip()
        records['kitchenName']    = records['kitchenName'].str.strip()

        all_records.append(records)
        log.info(f"  {curr_date}: version {version_key} → {len(records):,} rows")

        # Save day-by-day
        master_df = records.copy()
        master_df = master_df.rename(columns={
            'date_parsed': 'date',
            'ingredientCode': 'sku_code',
            'ingredientName': 'sku',
            'kitchenCode': 'outlet_code',
            'kitchenName': 'outlet'
        })
        master_df['date'] = pd.to_datetime(master_df['date']).dt.strftime('%Y-%m-%d')
        master_df = master_df.groupby(["date", "sku_code", "outlet_code"], as_index=False).agg(
            sku=("sku", "first"),
            outlet=("outlet", "first"),
            qty_sold=("qty_sold", "sum")
        )
        try:
            import sys
            if os.path.dirname(os.path.dirname(os.path.abspath(__file__))) not in sys.path:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from backend.database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            inserted = 0
            for _, row in master_df.iterrows():
                try:
                    cursor.execute("""
                        INSERT INTO fact_daily_sales (date, sku, sku_code, outlet, outlet_code, qty_sold)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, sku_code, outlet_code) DO UPDATE SET
                            qty_sold = EXCLUDED.qty_sold,
                            sku = EXCLUDED.sku,
                            outlet = EXCLUDED.outlet
                    """, (row["date"], row["sku"], row["sku_code"], row["outlet"], row["outlet_code"], row["qty_sold"]))
                    inserted += 1
                except Exception as e:
                    pass
            conn.commit()
            cursor.close()
            conn.close()
            log.info(f"  Saved {inserted} rows to DB for {curr_date}")
        except Exception as e:
            log.error(f"  Failed to save DB for {curr_date}: {e}")

        curr_date -= timedelta(days=1)

    if not all_records:
        log.error("No data collected!")
        return

        # Combine all days
    master_df = pd.concat(all_records, ignore_index=True)
    master_df = master_df.rename(columns={
        'date_parsed': 'date',
        'ingredientCode': 'sku_code',
        'ingredientName': 'sku',
        'kitchenCode': 'outlet_code',
        'kitchenName': 'outlet'
    })
    master_df['date'] = pd.to_datetime(master_df['date']).dt.strftime('%Y-%m-%d')

    # Deduplicate using CODES (not names) — codes have 0 duplicates vs 619 for names
    master_df = master_df.groupby(["date", "sku_code", "outlet_code"], as_index=False).agg(
        sku=("sku", "first"),
        outlet=("outlet", "first"),
        qty_sold=("qty_sold", "sum")
    )
    
    # Upsert into PostgreSQL
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()

        log.info(f"Uploading {len(master_df)} rows to fact_daily_sales ...")
        inserted = 0
        for _, row in master_df.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO fact_daily_sales (date, sku, sku_code, outlet, outlet_code, qty_sold)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date, sku_code, outlet_code) DO UPDATE SET
                        qty_sold = EXCLUDED.qty_sold,
                        sku = EXCLUDED.sku,
                        outlet = EXCLUDED.outlet
                """, (row["date"], row["sku"], row["sku_code"], row["outlet"], row["outlet_code"], row["qty_sold"]))
                inserted += 1
            except Exception as e:
                log.warning(f"DB Insert error: {e}")

        conn.commit()
        cursor.close()
        conn.close()
        log.info(f"Done! Upserted {inserted:,} records into PostgreSQL.")

    except Exception as e:
        log.error(f"DB connection failed: {e}")
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supplynote_demand_backup.csv")
        master_df.to_csv(fallback, index=False)
        log.info(f"Saved to fallback CSV: {fallback}")



if __name__ == "__main__":
    run()

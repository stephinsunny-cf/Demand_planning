"""
Targeted Importer for Missing Dates Only
Identifies missing dates in pos_orders and fetches SupplyNote S3 CSVs ONLY for those dates.
"""
import os
import re
import io
import sys
import logging
import requests
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s")
log = logging.getLogger("missing_dates_importer")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import query_df, get_db_connection

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

SN_USERNAME = os.getenv("SUPPLYNOTE_USER") or os.getenv("SN_USERNAME", "")
SN_PASSWORD = os.getenv("SUPPLYNOTE_PASSWORD") or os.getenv("SN_PASS", "")
BUSINESS_ID = "65b205675255c93a41dd7849"
BASE = "https://www.supplynote.in/api"
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
IST = timezone(timedelta(hours=5, minutes=30))

def login() -> str:
    for url in ["https://www.supplynote.in/api/auth/signin", "https://www.supplynote.in/api/auth/login"]:
        for body in [{"username": SN_USERNAME, "password": SN_PASSWORD}, {"email": SN_USERNAME, "password": SN_PASSWORD}]:
            try:
                res = requests.post(url, json=body, timeout=20)
                if res.status_code in (200, 201):
                    m = JWT_RE.search(res.text)
                    if m:
                        log.info("Login successful — JWT obtained.")
                        return m.group(0)
            except Exception:
                pass
    raise RuntimeError("SupplyNote Login Failed")

def get_missing_dates() -> list[date]:
    po_dates = query_df("SELECT distinct date(created_at_ist) as date FROM pos_orders WHERE created_at_ist IS NOT NULL ORDER BY date")
    if po_dates.empty:
        return []
    min_d = pd.to_datetime(po_dates['date'].min()).date()
    max_d = pd.to_datetime(po_dates['date'].max()).date()
    full_range = pd.date_range(min_d, max_d).date
    present_dates = set(pd.to_datetime(po_dates['date']).dt.date)
    return [d for d in full_range if d not in present_dates]

def date_to_plan_date(d: date) -> str:
    midnight_ist = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    return midnight_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def get_version_key(token: str, target_date: date) -> str | None:
    plan_date = date_to_plan_date(target_date)
    url = f"{BASE}/demandplan/history/semiFinished?business={BUSINESS_ID}&planDate={requests.utils.quote(plan_date)}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.ok:
            versions = res.json()
            versions = versions if isinstance(versions, list) else versions.get("data", [])
            if versions:
                return versions[0].get("versionKey")
    except Exception as e:
        log.warning(f"Error fetching version key for {target_date}: {e}")
    return None

def get_download_url(session: requests.Session, token: str, version_key: str) -> str | None:
    url = f"{BASE}/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    import time
    for attempt in range(5):
        try:
            log.info(f"  Requesting S3 URL for version {version_key} (attempt {attempt+1}/5)...")
            res = session.get(url, headers=headers, timeout=120)
            if res.ok:
                return res.json().get("data")
            if res.status_code == 504:
                time.sleep(15)
        except requests.exceptions.ReadTimeout:
            time.sleep(15)
    return None

def run():
    missing_dates = get_missing_dates()
    if not missing_dates:
        log.info("No missing dates found in pos_orders! Everything is 100% complete.")
        return

    log.info(f"Found {len(missing_dates)} missing dates to fetch: {[str(d) for d in missing_dates]}")
    token = login()
    session = requests.Session()

    seen_versions = set()
    all_records = []

    for dt in missing_dates:
        vk = get_version_key(token, dt)
        if not vk:
            log.warning(f"  No version key found on SupplyNote for missing date {dt}")
            continue

        if vk in seen_versions:
            log.info(f"  Date {dt} uses version {vk} (already downloaded in this batch).")
            continue
        seen_versions.add(vk)

        s3_url = get_download_url(session, token, vk)
        if not s3_url:
            log.warning(f"  Failed to get S3 URL for version {vk}")
            continue

        try:
            res = requests.get(s3_url, timeout=180)
            if res.ok:
                df = pd.read_csv(io.StringIO(res.content.decode("utf-8-sig", errors="replace")))
                if 'ingredientCode' in df.columns and 'plannedDemand' in df.columns:
                    df['date_parsed'] = pd.to_datetime(df.get('date', str(dt)), format='%d-%m-%Y', errors='coerce').fillna(dt)
                    df['qty_sold'] = pd.to_numeric(df['plannedDemand'], errors='coerce').fillna(0)
                    recs = df[['date_parsed', 'ingredientCode', 'ingredientName', 'kitchenCode', 'kitchenName', 'qty_sold']].copy()
                    recs = recs[recs['qty_sold'] > 0]
                    recs['ingredientCode'] = recs['ingredientCode'].astype(str).str.strip()
                    recs['ingredientName'] = recs['ingredientName'].astype(str).str.strip()
                    recs['kitchenCode']    = recs['kitchenCode'].astype(str).str.strip()
                    recs['kitchenName']    = recs['kitchenName'].astype(str).str.strip()
                    all_records.append(recs)
                    log.info(f"  Successfully downloaded data for version {vk} ({len(recs):,} rows)")
        except Exception as e:
            log.error(f"Error downloading/processing CSV for {dt}: {e}")

    if not all_records:
        log.warning("No records collected for missing dates.")
        return

    master_df = pd.concat(all_records, ignore_index=True)
    master_df = master_df.rename(columns={
        'date_parsed': 'date', 'ingredientCode': 'sku_code',
        'ingredientName': 'sku', 'kitchenCode': 'outlet_code', 'kitchenName': 'outlet'
    })
    master_df['date'] = pd.to_datetime(master_df['date']).dt.strftime('%Y-%m-%d')
    master_df = master_df.groupby(["date", "sku_code", "outlet_code"], as_index=False).agg(
        sku=("sku", "first"), outlet=("outlet", "first"), qty_sold=("qty_sold", "sum")
    )

    conn = get_db_connection()
    cursor = conn.cursor()
    log.info(f"Upserting {len(master_df):,} missing rows into fact_daily_sales...")
    inserted = 0
    for _, row in master_df.iterrows():
        try:
            cursor.execute("""
                INSERT INTO fact_daily_sales (date, sku, sku_code, outlet, outlet_code, qty_sold)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, sku_code, outlet_code) DO UPDATE SET
                    qty_sold = EXCLUDED.qty_sold, sku = EXCLUDED.sku, outlet = EXCLUDED.outlet
            """, (row["date"], row["sku"], row["sku_code"], row["outlet"], row["outlet_code"], row["qty_sold"]))
            inserted += 1
        except Exception as e:
            pass
    conn.commit()
    cursor.close()
    conn.close()
    log.info(f"DONE! Upserted {inserted:,} records for missing dates into PostgreSQL.")

if __name__ == "__main__":
    run()

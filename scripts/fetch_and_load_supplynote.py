"""
fetch_and_load_supplynote.py
============================
Bulletproof pipeline:
  For each date from 2026-01-01 to 2026-07-23:
    1. Get version key for that date from SupplyNote API
    2. Request the S3 CSV download URL (wait patiently up to 15 min if server is still building it)
    3. Download the CSV directly into memory (no disk save)
    4. Parse with CORRECT dayfirst=True date format
    5. Bulk UPSERT into PostgreSQL using COPY + temp table (fast, no row-by-row)
    6. Log success and move to next date

No intermediate files. No second script needed.
"""

import io
import os
import re
import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "supplynote_reload.log"),
            encoding="utf-8"
        )
    ]
)
log = logging.getLogger("sn_reload")

# ── Config ─────────────────────────────────────────────────────────────────────
SN_USERNAME = os.getenv("SUPPLYNOTE_USER") or os.getenv("SN_USERNAME", "")
SN_PASSWORD = os.getenv("SUPPLYNOTE_PASSWORD") or os.getenv("SN_PASS", "")
BUSINESS_ID = "65b205675255c93a41dd7849"
BASE        = "https://www.supplynote.in/api"
IST         = timezone(timedelta(hours=5, minutes=30))
JWT_RE      = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")

START_DATE  = date(2026, 1, 1)
END_DATE    = date(2026, 7, 23)   # Exact 6-month window as specified


# ── DB Connection ──────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASS"),
        dbname=os.getenv("PG_DB"),
        port=os.getenv("PG_PORT", "5432"),
        connect_timeout=30,
        keepalives=1,
        keepalives_idle=15,
        keepalives_interval=5,
        keepalives_count=5,
    )


# ── SupplyNote Auth ────────────────────────────────────────────────────────────
def login() -> str:
    for url in ["https://www.supplynote.in/api/auth/signin", "https://www.supplynote.in/api/auth/login"]:
        for body in [
            {"username": SN_USERNAME, "password": SN_PASSWORD},
            {"email": SN_USERNAME, "password": SN_PASSWORD},
        ]:
            try:
                res = requests.post(url, json=body, timeout=20)
                if res.status_code == 404:
                    break
                if res.status_code in (200, 201):
                    data = res.json()
                    # Search for JWT anywhere in the response
                    token = _find_jwt(data) or JWT_RE.search(res.text)
                    if token:
                        if isinstance(token, str):
                            log.info("Login successful — JWT obtained.")
                            return token
                        log.info("Login successful — JWT obtained.")
                        return token.group(0)
            except Exception as e:
                log.warning(f"Login attempt error: {e}")
    raise RuntimeError("Could not login to SupplyNote. Check credentials in .env")


def _find_jwt(data) -> str | None:
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, str) and JWT_RE.match(v):
                return v
            found = _find_jwt(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_jwt(item)
            if found:
                return found
    return None


# ── SupplyNote API Calls ───────────────────────────────────────────────────────
def get_version_key(session: requests.Session, target_date: date) -> str | None:
    """Get the versionKey for a given date."""
    midnight_ist = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=IST)
    plan_date = midnight_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    url = f"{BASE}/demandplan/history/semiFinished?business={BUSINESS_ID}&planDate={requests.utils.quote(plan_date)}"
    try:
        res = session.get(url, timeout=30)
        if not res.ok:
            return None
        versions = res.json()
        versions = versions if isinstance(versions, list) else versions.get("data", [])
        if not versions:
            return None
        return versions[0].get("versionKey")
    except Exception as e:
        log.warning(f"  {target_date}: get_version_key error: {e}")
        return None


def get_s3_url(session: requests.Session, version_key: str) -> str | None:
    """
    Request the S3 download URL. SupplyNote builds the file server-side which can take
    several minutes. We poll patiently for up to 15 minutes with 60-second intervals.
    """
    url = f"{BASE}/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}"
    max_wait_seconds = 900   # 15 minutes maximum
    poll_interval    = 60    # check every 60 seconds
    elapsed          = 0

    while elapsed < max_wait_seconds:
        try:
            log.info(f"    Requesting S3 URL for version {version_key} (elapsed {elapsed}s)...")
            res = session.get(url, timeout=300)  # 5-minute socket timeout

            if res.status_code in (200, 201):
                data = res.json()
                s3_url = data.get("data") or data.get("url")
                if s3_url:
                    log.info(f"    S3 URL obtained!")
                    return s3_url
                log.warning(f"    200 OK but no URL in response: {str(data)[:200]}")
                return None

            elif res.status_code in (202, 504, 503):
                log.info(f"    Server still building file (HTTP {res.status_code}). Waiting {poll_interval}s...")
                time.sleep(poll_interval)
                elapsed += poll_interval
                continue

            else:
                log.warning(f"    Unexpected HTTP {res.status_code}: {res.text[:200]}")
                return None

        except requests.exceptions.ReadTimeout:
            log.info(f"    ReadTimeout (server is processing). Waiting {poll_interval}s and retrying...")
            time.sleep(poll_interval)
            elapsed += poll_interval
        except Exception as e:
            log.warning(f"    S3 URL fetch error: {e}")
            return None

    log.error(f"    Gave up waiting for S3 URL after {max_wait_seconds}s for version {version_key}")
    return None


def download_csv_to_df(s3_url: str) -> pd.DataFrame | None:
    """Download CSV from S3 directly into a DataFrame in memory."""
    for attempt in range(3):
        try:
            log.info(f"    Downloading CSV from S3 (attempt {attempt+1}/3)...")
            res = requests.get(s3_url, timeout=300)
            if not res.ok:
                log.warning(f"    S3 download failed: HTTP {res.status_code}")
                return None
            content = res.content.decode("utf-8-sig", errors="replace")
            df = pd.read_csv(io.StringIO(content))
            log.info(f"    Downloaded {len(df):,} rows, columns: {list(df.columns)}")
            return df
        except requests.exceptions.ReadTimeout:
            log.warning(f"    Timeout downloading CSV. Retrying in 10s...")
            time.sleep(10)
        except Exception as e:
            log.warning(f"    CSV download error: {e}")
            return None
    return None


# ── Parse & Validate ───────────────────────────────────────────────────────────
def parse_and_validate(df: pd.DataFrame, fallback_date: date) -> pd.DataFrame | None:
    """
    Parse the raw SupplyNote CSV and return a clean DataFrame with columns:
    [date, sku, sku_code, outlet, outlet_code, qty_sold]

    CRITICAL: Use explicit format '%d-%m-%Y' for dates. If the date column is missing
    or unparseable, fall back to the API date (fallback_date).
    """
    required = {"ingredientCode", "kitchenCode", "ingredientName", "kitchenName", "plannedDemand"}
    missing  = required - set(df.columns)
    if missing:
        log.warning(f"    Missing expected columns: {missing}. Available: {list(df.columns)}")
        return None

    # Parse the date column correctly (SupplyNote exports DD-MM-YYYY)
    if "date" in df.columns:
        df["date_parsed"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        bad = df["date_parsed"].isna().sum()
        if bad > 0:
            log.warning(f"    {bad} rows had unparseable dates — filling with {fallback_date}")
        df["date_parsed"] = df["date_parsed"].fillna(pd.Timestamp(fallback_date))
    else:
        df["date_parsed"] = pd.Timestamp(fallback_date)

    # Build clean record set
    records = df[["date_parsed", "ingredientCode", "ingredientName", "kitchenCode", "kitchenName", "plannedDemand"]].copy()
    records.columns = ["date", "sku_code", "sku", "outlet_code", "outlet", "qty_sold"]

    # Sanitise
    records["sku_code"]    = records["sku_code"].astype(str).str.strip()
    records["outlet_code"] = records["outlet_code"].astype(str).str.strip()
    records["sku"]         = records["sku"].astype(str).str.strip()
    records["outlet"]      = records["outlet"].astype(str).str.strip()
    records["qty_sold"]    = pd.to_numeric(records["qty_sold"], errors="coerce").fillna(0.0)
    records["date"]        = pd.to_datetime(records["date"]).dt.strftime("%Y-%m-%d")

    # Aggregate (one row per date+sku_code+outlet_code) — use codes as the unique key
    records = records.groupby(["date", "sku_code", "outlet_code"], as_index=False).agg(
        sku=("sku", "first"),
        outlet=("outlet", "first"),
        qty_sold=("qty_sold", "sum")
    )

    # Safety: drop any rows outside the valid 6-month window
    records["date"] = pd.to_datetime(records["date"])
    records = records[
        (records["date"] >= pd.Timestamp(START_DATE)) &
        (records["date"] <= pd.Timestamp(END_DATE))
    ]
    records["date"] = records["date"].dt.strftime("%Y-%m-%d")

    log.info(f"    Parsed to {len(records):,} clean rows for date window.")
    return records


# ── Bulk Upsert ────────────────────────────────────────────────────────────────
def bulk_upsert(df: pd.DataFrame) -> int:
    """
    Use PostgreSQL COPY into a temp table, then INSERT ... ON CONFLICT DO UPDATE.
    This is orders of magnitude faster than row-by-row inserts.
    Returns number of rows upserted.
    """
    if df.empty:
        return 0

    conn = get_conn()
    try:
        cursor = conn.cursor()
        chunk_size = 100_000
        total_upserted = 0

        for i in range(0, len(df), chunk_size):
            chunk = df.iloc[i:i+chunk_size][["date", "sku", "sku_code", "outlet", "outlet_code", "qty_sold"]]

            # Write chunk to CSV buffer
            buf = io.StringIO()
            chunk.to_csv(buf, index=False, header=True)
            buf.seek(0)

            cursor.execute("""
                CREATE TEMP TABLE IF NOT EXISTS _tmp_sn_load (
                    date TEXT, sku TEXT, sku_code TEXT,
                    outlet TEXT, outlet_code TEXT, qty_sold FLOAT
                ) ON COMMIT DELETE ROWS;
            """)
            cursor.copy_expert(
                "COPY _tmp_sn_load(date, sku, sku_code, outlet, outlet_code, qty_sold) FROM STDIN WITH CSV HEADER",
                buf
            )
            cursor.execute("""
                INSERT INTO fact_daily_sales (date, sku, sku_code, outlet, outlet_code, qty_sold)
                SELECT date::DATE, sku, sku_code, outlet, outlet_code, qty_sold FROM _tmp_sn_load
                ON CONFLICT (date, sku, outlet) DO UPDATE SET
                    qty_sold    = EXCLUDED.qty_sold,
                    sku_code    = EXCLUDED.sku_code,
                    outlet_code = EXCLUDED.outlet_code;
            """)
            conn.commit()
            total_upserted += len(chunk)
            log.info(f"    Committed chunk {i//chunk_size + 1} ({len(chunk):,} rows)")

        cursor.close()

        # ── Auto-populate dim_sku and dim_outlet from this batch ──────────────
        # Every unique code+name pair seen is upserted — builds lookup over time
        dim_df = df[["sku_code", "sku"]].drop_duplicates("sku_code")
        if not dim_df.empty:
            cursor2 = conn.cursor()
            from psycopg2.extras import execute_values
            execute_values(cursor2, """
                INSERT INTO dim_sku (sku_code, sku_name, is_tracked)
                VALUES %s
                ON CONFLICT (sku_code) DO UPDATE SET
                    sku_name   = EXCLUDED.sku_name,
                    updated_at = NOW()
                WHERE dim_sku.is_tracked = FALSE
            """, [(r["sku_code"], r["sku"], False) for _, r in dim_df.iterrows()])
            conn.commit()
            cursor2.close()
            log.info(f"    dim_sku: {len(dim_df)} codes synced")

        outlet_df = df[["outlet_code", "outlet"]].drop_duplicates("outlet_code")
        if not outlet_df.empty:
            cursor3 = conn.cursor()
            execute_values(cursor3, """
                INSERT INTO dim_outlet (outlet_code, outlet_name)
                VALUES %s
                ON CONFLICT (outlet_code) DO UPDATE SET
                    outlet_name = EXCLUDED.outlet_name,
                    updated_at  = NOW()
            """, [(r["outlet_code"], r["outlet"]) for _, r in outlet_df.iterrows()])
            conn.commit()
            cursor3.close()
            log.info(f"    dim_outlet: {len(outlet_df)} outlets synced")

        return total_upserted
    except Exception as e:
        conn.rollback()
        log.error(f"    Bulk upsert failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()


# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    log.info("=" * 70)
    log.info(f"SupplyNote Reload | {START_DATE} → {END_DATE}")
    log.info("=" * 70)

    session = requests.Session()
    token = login()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.supplynote.in/demandplans/history",
        "Origin": "https://www.supplynote.in",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # Walk backwards (most recent first)
    curr_date        = END_DATE
    seen_versions    = set()
    days_done        = 0
    days_skipped     = 0
    total_rows_saved = 0
    total_days       = (END_DATE - START_DATE).days + 1

    while curr_date >= START_DATE:
        log.info(f"\n[{(END_DATE - curr_date).days + 1}/{total_days}] Processing {curr_date} ...")

        # Step 1: Get version key
        version_key = get_version_key(session, curr_date)
        if not version_key:
            log.info(f"  No version found for {curr_date} — skipping.")
            days_skipped += 1
            curr_date -= timedelta(days=1)
            continue

        if version_key in seen_versions:
            log.info(f"  Version {version_key} already processed — skipping duplicate.")
            curr_date -= timedelta(days=1)
            continue
        seen_versions.add(version_key)

        # Step 2: Get S3 URL (patient polling)
        s3_url = get_s3_url(session, version_key)
        if not s3_url:
            log.warning(f"  Could not get S3 URL for {curr_date}. Skipping.")
            days_skipped += 1
            curr_date -= timedelta(days=1)
            continue

        # Step 3: Download CSV into memory
        df_raw = download_csv_to_df(s3_url)
        if df_raw is None or df_raw.empty:
            log.warning(f"  Empty/failed CSV for {curr_date}. Skipping.")
            days_skipped += 1
            curr_date -= timedelta(days=1)
            continue

        # Step 4: Parse correctly (DD-MM-YYYY, no American format mangling!)
        df_clean = parse_and_validate(df_raw, curr_date)
        if df_clean is None or df_clean.empty:
            log.warning(f"  Parse failed for {curr_date}. Skipping.")
            days_skipped += 1
            curr_date -= timedelta(days=1)
            continue

        # Step 5: Bulk upsert directly into PostgreSQL
        rows_saved = bulk_upsert(df_clean)
        total_rows_saved += rows_saved
        days_done += 1
        log.info(f"  ✓ {curr_date}: {rows_saved:,} rows upserted. Total so far: {total_rows_saved:,}")

        curr_date -= timedelta(days=1)

    log.info("\n" + "=" * 70)
    log.info(f"DONE! Days processed: {days_done} | Days skipped: {days_skipped}")
    log.info(f"Total rows upserted into fact_daily_sales: {total_rows_saved:,}")
    log.info("=" * 70)


if __name__ == "__main__":
    run()

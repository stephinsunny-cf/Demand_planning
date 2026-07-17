"""
sync_urbanpiper_daily.py
------------------------
Nightly sync of 4 UrbanPiper POS tables via Metabase API → PostgreSQL.

Features:
  - Change detection: checks if Metabase has data newer than what's in the DB.
    Skips the download entirely if there is nothing new.
  - Aggressive deduplication before any INSERT:
      * Removes sign=-1 UrbanPiper tombstone rows
      * Removes fully duplicate rows
      * Removes key-level duplicates (keeps latest)
  - ON CONFLICT DO NOTHING so repeated runs are always safe.

Runs nightly at 2:00 AM IST inside the GitHub Actions workflow.
"""

import os
import io
import json
import logging
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
METABASE_URL     = os.getenv("METABASE_URL", "https://clickhouse.eatfit.in")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")
METABASE_DB_ID   = 2  # urbanpiper ClickHouse DB in Metabase

PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER")
PG_PASS = os.getenv("PG_PASS")
PG_DB   = os.getenv("PG_DB")

IST = timezone(timedelta(hours=5, minutes=30))

# ── Table definitions ──────────────────────────────────────────────────────
TABLES = [
    {
        "source":    "orders",
        "dest":      "pos_orders",
        "date_col":  "created_at_ist",
        "dedup_key": ["id"],
        "desc":      "Order transactions (revenue, channel, store, brand)",
    },
    {
        "source":    "order_items",
        "dest":      "pos_order_items",
        "date_col":  "order_created_at_ist",
        "dedup_key": ["id"],
        "desc":      "Line items — which dishes were sold",
    },
    {
        "source":    "item_options",
        "dest":      "pos_item_options",
        "date_col":  "order_created_at_ist",
        "dedup_key": ["id"],
        "desc":      "Add-ons / customisations on order items",
    },
    {
        "source":    "orders_state_transitions",
        "dest":      "pos_orders_state_transitions",
        "date_col":  "status_changed_at_ist",
        "dedup_key": ["order_id", "from_status", "to_status"],
        "desc":      "Order lifecycle events (placed→dispatched→delivered)",
    },
]

# ── DB helpers ─────────────────────────────────────────────────────────────
def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        dbname=PG_DB
    )


def get_pg_latest(conn, dest_table: str, date_col: str) -> str | None:
    """Return the latest date_col value we already have in PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT MAX(\"{date_col}\") FROM {dest_table}"
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] else None
    

# ── Metabase helpers ───────────────────────────────────────────────────────
def metabase_get_max(table_name: str, date_col: str) -> str | None:
    """Ask Metabase for the MAX timestamp in the source table (change detection)."""
    query = f"SELECT MAX({date_col}) AS max_ts FROM `curefoods_test`.`{table_name}`"
    payload   = {"database": METABASE_DB_ID, "type": "native", "native": {"query": query}}
    headers   = {"x-api-key": METABASE_API_KEY}
    form_data = {"query": json.dumps(payload)}

    try:
        res = requests.post(
            f"{METABASE_URL}/api/dataset/csv",
            headers=headers, data=form_data, timeout=60,
        )
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text), on_bad_lines="skip")
            if not df.empty and "max_ts" in df.columns:
                return str(df["max_ts"].iloc[0])
    except Exception as exc:
        log.error("  Failed to get MAX from Metabase for %s: %s", table_name, exc)
    return None


def fetch_from_metabase(table_name: str, date_col: str, start_dt: str, end_dt: str):
    """Download data for a date window from Metabase."""
    query = (
        f"SELECT * FROM `curefoods_test`.`{table_name}` "
        f"WHERE {date_col} >= '{start_dt}' AND {date_col} < '{end_dt}'"
    )
    payload   = {"database": METABASE_DB_ID, "type": "native", "native": {"query": query}}
    headers   = {"x-api-key": METABASE_API_KEY}
    form_data = {"query": json.dumps(payload)}

    log.info("  Downloading: %s [%s → %s]", table_name, start_dt, end_dt)
    try:
        res = requests.post(
            f"{METABASE_URL}/api/dataset/csv",
            headers=headers, data=form_data, timeout=180,
        )
    except requests.exceptions.Timeout:
        log.error("  Request timed out for %s", table_name)
        return None

    if res.status_code != 200:
        log.error("  Metabase error %s: %s", res.status_code, res.text[:200])
        return None

    try:
        df = pd.read_csv(io.StringIO(res.text), on_bad_lines="skip", low_memory=False)
        log.info("  Raw rows: %d", len(df))
        return df
    except Exception as exc:
        log.error("  CSV parse error: %s", exc)
        return None


# ── Deduplication ──────────────────────────────────────────────────────────
def clean_and_dedup(df: pd.DataFrame, dedup_key: list) -> pd.DataFrame:
    """
    1. Normalise column names.
    2. Remove sign=-1 tombstone rows (UrbanPiper ReplacingMergeTree deletes).
    3. Drop fully duplicate rows.
    4. Drop key-level duplicates (keep last = most recent version).
    5. Replace NaN with None for PostgreSQL.
    """
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    # Step 2 – tombstones
    if "sign" in df.columns:
        before = len(df)
        df = df[df["sign"].astype(str) == "1"].copy()
        removed = before - len(df)
        if removed:
            log.info("  Removed %d sign=-1 tombstone rows", removed)

    # Step 3 – full duplicates
    before = len(df)
    df = df.drop_duplicates()
    if before - len(df):
        log.info("  Removed %d fully duplicate rows", before - len(df))

    # Step 4 – key-level dedup
    available_keys = [k for k in dedup_key if k in df.columns]
    if available_keys:
        before = len(df)
        df = df.drop_duplicates(subset=available_keys, keep="last")
        if before - len(df):
            log.info("  Removed %d key-level duplicates (kept latest)", before - len(df))

    # Step 5 – NaN → None
    df = df.where(pd.notnull(df), None)
    return df


# ── PostgreSQL upsert ──────────────────────────────────────────────────────
def ensure_table_and_upsert(conn, df: pd.DataFrame, dest_table: str, dedup_key: list) -> int:
    """Create table if needed, add missing columns, bulk-insert skipping conflicts."""
    if df.empty:
        return 0

    cols = list(df.columns)
    rows = [
        tuple(str(v) if v is not None else None for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    with conn.cursor() as cur:
        # Create table
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f'CREATE TABLE IF NOT EXISTS {dest_table} ({col_defs})')
        conn.commit()

        # Add any new columns
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (dest_table,),
        )
        existing = {row[0] for row in cur.fetchall()}
        for col in cols:
            if col not in existing:
                cur.execute(f'ALTER TABLE {dest_table} ADD COLUMN "{col}" TEXT')
        conn.commit()

        # Ensure unique constraint for ON CONFLICT
        available_keys = [k for k in dedup_key if k in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)

        if available_keys:
            key_str = ", ".join(f'"{k}"' for k in available_keys)
            try:
                cur.execute(
                    f"ALTER TABLE {dest_table} ADD CONSTRAINT {dest_table}_uq UNIQUE ({key_str})"
                )
                conn.commit()
            except Exception:
                conn.rollback()

            insert_sql = (
                f"INSERT INTO {dest_table} ({col_str}) VALUES %s "
                f"ON CONFLICT ({key_str}) DO NOTHING"
            )
        else:
            insert_sql = f"INSERT INTO {dest_table} ({col_str}) VALUES %s ON CONFLICT DO NOTHING"

        execute_values(cur, insert_sql, rows, page_size=500)
        conn.commit()

    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────
def run():
    if not METABASE_API_KEY:
        log.error("METABASE_API_KEY is not set. Aborting.")
        return

    today     = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    start_dt  = yesterday.strftime("%Y-%m-%d %H:%M:%S")
    end_dt    = today.strftime("%Y-%m-%d %H:%M:%S")

    log.info("=" * 65)
    log.info("UrbanPiper Daily Sync  |  window: %s → %s", start_dt, end_dt)
    log.info("=" * 65)

    conn       = get_pg_conn()
    total_rows = 0

    for tbl in TABLES:
        log.info("\n[%s → %s]  %s", tbl["source"], tbl["dest"], tbl["desc"])

        # ── Change Detection ──────────────────────────────────────────────
        log.info("  Checking for new data in Metabase...")
        mb_max = metabase_get_max(tbl["source"], tbl["date_col"])

        # Check what we already have in PostgreSQL
        try:
            pg_max = get_pg_latest(conn, tbl["dest"], tbl["date_col"])
        except Exception:
            pg_max = None  # table doesn't exist yet

        log.info("  Metabase latest : %s", mb_max or "unknown")
        log.info("  PostgreSQL latest: %s", pg_max or "nothing yet")

        if mb_max and pg_max and mb_max <= pg_max:
            log.info("  No new data detected — skipping download.")
            continue

        log.info("  New data detected! Downloading...")

        # ── Fetch ─────────────────────────────────────────────────────────
        df = fetch_from_metabase(tbl["source"], tbl["date_col"], start_dt, end_dt)
        if df is None or df.empty:
            log.warning("  No rows returned — skipping.")
            continue

        # ── Clean & Dedup ──────────────────────────────────────────────────
        df = clean_and_dedup(df, tbl["dedup_key"])
        log.info("  Clean rows after dedup: %d", len(df))

        # ── Insert ─────────────────────────────────────────────────────────
        inserted = ensure_table_and_upsert(conn, df, tbl["dest"], tbl["dedup_key"])
        log.info("  Rows inserted into %s: %d", tbl["dest"], inserted)
        total_rows += inserted

    conn.close()
    log.info("\n" + "=" * 65)
    log.info("Sync complete.  Total rows inserted: %d", total_rows)
    log.info("=" * 65)


if __name__ == "__main__":
    run()

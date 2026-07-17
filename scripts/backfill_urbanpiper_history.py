"""
backfill_urbanpiper_history.py
-------------------------------
One-time historical backfill: downloads ALL data for 4 UrbanPiper tables
from 2026-01-01 to today, month by month, with aggressive deduplication
before inserting into PostgreSQL.

Run once manually:
    python scripts/backfill_urbanpiper_history.py
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

# ── Historical date range ───────────────────────────────────────────────────
# Jan 2026 to today
START_DATE = datetime(2026, 1, 1)
IST        = timezone(timedelta(hours=5, minutes=30))
END_DATE   = datetime.now(IST).replace(tzinfo=None)  # naive local time

# ── Primary key columns for deduplication per table ────────────────────────
# 'sign' column in UrbanPiper ClickHouse is a ReplacingMergeTree sign (+1/-1).
# The actual unique key is 'id' for orders / order_items / item_options.
# For state_transitions there is no 'id', so we dedup on composite key.
TABLES = [
    {
        "source":    "orders",
        "dest":      "pos_orders",
        "date_col":  "created_at_ist",
        "dedup_key": ["id"],          # order's unique ID
        "desc":      "Order transactions",
    },
    {
        "source":    "order_items",
        "dest":      "pos_order_items",
        "date_col":  "order_created_at_ist",
        "dedup_key": ["id"],          # order item unique ID
        "desc":      "Order line items (dishes sold)",
    },
    {
        "source":    "item_options",
        "dest":      "pos_item_options",
        "date_col":  "order_created_at_ist",
        "dedup_key": ["id"],          # item option unique ID
        "desc":      "Add-ons / customisations",
    },
    {
        "source":    "orders_state_transitions",
        "dest":      "pos_orders_state_transitions",
        "date_col":  "status_changed_at_ist",
        "dedup_key": ["order_id", "from_status", "to_status"],
        "desc":      "Order lifecycle events",
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────
def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        dbname=PG_DB
    )


def month_chunks(start: datetime, end: datetime):
    """Yield (start_str, end_str) for each calendar month between start and end."""
    cursor = start.replace(day=1)
    while cursor < end:
        month_end = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        chunk_end = min(month_end, end)
        yield cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cursor = month_end


def fetch_chunk(table_name: str, date_col: str, start_dt: str, end_dt: str):
    """Query Metabase and return a DataFrame for the given date range."""
    query = (
        f"SELECT * FROM `curefoods_test`.`{table_name}` "
        f"WHERE {date_col} >= '{start_dt}' AND {date_col} < '{end_dt}'"
    )
    payload   = {"database": METABASE_DB_ID, "type": "native", "native": {"query": query}}
    headers   = {"x-api-key": METABASE_API_KEY}
    form_data = {"query": json.dumps(payload)}

    try:
        res = requests.post(
            f"{METABASE_URL}/api/dataset/csv",
            headers=headers, data=form_data, timeout=180,
        )
    except requests.exceptions.Timeout:
        log.error("    Timeout for %s [%s→%s]", table_name, start_dt, end_dt)
        return None

    if res.status_code != 200:
        log.error("    Metabase error %s: %s", res.status_code, res.text[:200])
        return None

    try:
        df = pd.read_csv(io.StringIO(res.text), on_bad_lines="skip", low_memory=False)
        return df
    except Exception as exc:
        log.error("    CSV parse error: %s", exc)
        return None


def clean_and_dedup(df: pd.DataFrame, dedup_key: list) -> pd.DataFrame:
    """Normalise columns, remove UrbanPiper sign=-1 tombstones, and deduplicate."""
    # Normalise column names
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    initial = len(df)

    # UrbanPiper uses a ReplacingMergeTree with a 'sign' column:
    # sign=+1 → INSERT, sign=-1 → DELETE/cancel. Keep only sign=1 rows.
    if "sign" in df.columns:
        df = df[df["sign"].astype(str) == "1"].copy()
        log.info("    Removed %d sign=-1 tombstone rows", initial - len(df))

    # Drop fully duplicate rows
    before = len(df)
    df = df.drop_duplicates()
    if before - len(df):
        log.info("    Removed %d fully duplicate rows", before - len(df))

    # Keep only the latest record per natural key (handles re-delivered records)
    available_keys = [k for k in dedup_key if k in df.columns]
    if available_keys:
        before = len(df)
        # For tables that have an 'updated_at' or similar, sort by it;
        # otherwise just take first occurrence per key
        df = df.drop_duplicates(subset=available_keys, keep="last")
        if before - len(df):
            log.info("    Removed %d key-level duplicates (kept latest)", before - len(df))

    # Replace pandas NA with None for PostgreSQL
    df = df.where(pd.notnull(df), None)
    return df


def ensure_table(cur, dest_table: str, cols: list):
    """Create PostgreSQL table and add any missing columns."""
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
    cur.execute(f'CREATE TABLE IF NOT EXISTS {dest_table} ({col_defs})')

    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (dest_table,),
    )
    existing = {row[0] for row in cur.fetchall()}
    for col in cols:
        if col not in existing:
            log.info("  Adding column '%s' to %s", col, dest_table)
            cur.execute(f'ALTER TABLE {dest_table} ADD COLUMN "{col}" TEXT')


def upsert_chunk(conn, df: pd.DataFrame, dest_table: str, dedup_key: list):
    """Bulk-insert a clean DataFrame chunk, skipping already-present rows."""
    if df.empty:
        return 0

    cols = list(df.columns)
    rows = [
        tuple(str(v) if v is not None else None for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    with conn.cursor() as cur:
        ensure_table(cur, dest_table, cols)
        conn.commit()

        # Build conflict clause if we have known unique keys
        available_keys = [k for k in dedup_key if k in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)

        if available_keys:
            # Add unique constraint if not already there (safe to run repeatedly)
            key_str = ", ".join(f'"{k}"' for k in available_keys)
            try:
                constraint_name = f"{dest_table}_uq"
                cur.execute(
                    f"ALTER TABLE {dest_table} ADD CONSTRAINT {constraint_name} "
                    f"UNIQUE ({key_str})"
                )
                conn.commit()
            except psycopg2.errors.DuplicateTable:
                conn.rollback()
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
            except Exception:
                conn.rollback()

            insert_sql = (
                f"INSERT INTO {dest_table} ({col_str}) VALUES %s "
                f"ON CONFLICT ({key_str}) DO NOTHING"
            )
        else:
            insert_sql = (
                f"INSERT INTO {dest_table} ({col_str}) VALUES %s "
                f"ON CONFLICT DO NOTHING"
            )

        execute_values(cur, insert_sql, rows, page_size=500)
        conn.commit()

    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────
def run():
    if not METABASE_API_KEY:
        log.error("METABASE_API_KEY not set. Check your .env file.")
        return

    log.info("=" * 70)
    log.info("UrbanPiper HISTORICAL BACKFILL  |  %s → %s",
             START_DATE.strftime("%Y-%m-%d"), END_DATE.strftime("%Y-%m-%d"))
    log.info("=" * 70)

    conn = get_pg_conn()
    grand_total = 0

    for tbl in TABLES:
        log.info("\n\n[TABLE: %s → %s]  %s", tbl["source"], tbl["dest"], tbl["desc"])
        log.info("─" * 60)

        table_total = 0
        for start_dt, end_dt in month_chunks(START_DATE, END_DATE):
            log.info("  Chunk: %s → %s", start_dt, end_dt)
            df = fetch_chunk(tbl["source"], tbl["date_col"], start_dt, end_dt)
            if df is None or df.empty:
                log.info("    No data for this chunk, skipping.")
                continue

            log.info("    Raw rows fetched: %d", len(df))
            df = clean_and_dedup(df, tbl["dedup_key"])
            log.info("    Clean rows to insert: %d", len(df))

            inserted = upsert_chunk(conn, df, tbl["dest"], tbl["dedup_key"])
            table_total  += inserted
            grand_total  += inserted

        log.info("  Total inserted for %s: %d rows", tbl["dest"], table_total)

    conn.close()
    log.info("\n" + "=" * 70)
    log.info("BACKFILL COMPLETE.  Grand total rows inserted: %d", grand_total)
    log.info("=" * 70)


if __name__ == "__main__":
    run()

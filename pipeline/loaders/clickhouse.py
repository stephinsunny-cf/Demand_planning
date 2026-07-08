"""
pipeline/loaders/clickhouse.py
───────────────────────────────
ClickHouse loader — inserts DataFrames into local demand_planning tables.

Features:
  - Column mismatch detection and graceful handling
  - Row count logging before/after insert
  - OPTIMIZE TABLE for ReplacingMergeTree deduplication
  - Pipeline run metadata logging
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

REPLACING_TABLES = {
    "dim_menu_items",
    "dim_recipe_master",
    "dim_vendor_master",
    "dim_safety_stock",
}


# ── Connection ────────────────────────────────────────────────────────────────

def get_local_client():
    """Return a ClickHouse client for the local demand_planning database."""
    return clickhouse_connect.get_client(
        host=os.getenv("LOCAL_HOST", "localhost"),
        port=int(os.getenv("LOCAL_PORT", 8123)),
        username=os.getenv("LOCAL_USER", "default"),
        password=os.getenv("LOCAL_PASSWORD", "admin123"),
        database=os.getenv("LOCAL_DB", "demand_planning"),
        connect_timeout=10,
    )


# ── Schema inspection ─────────────────────────────────────────────────────────

def get_table_columns(client, table: str) -> list[str]:
    """Return column names of a table in """
    try:
        result = client.query(f"DESCRIBE TABLE {table}")
        return [row[0] for row in result.result_rows]
    except Exception as exc:
        log.error("Could not describe table %s: %s", table, exc)
        return []


# ── Insert helper ─────────────────────────────────────────────────────────────

def insert_df(df: pd.DataFrame, table: str, client=None) -> int:
    """
    Insert a DataFrame into <table>.

    Returns number of rows inserted.
    Handles column mismatches by keeping only columns that exist in the table.
    """
    if df is None or df.empty:
        log.info("insert_df: empty DataFrame for %s — skipping", table)
        return 0

    close_after = client is None
    if client is None:
        try:
            client = get_local_client()
        except Exception as exc:
            log.error("Cannot connect to local ClickHouse: %s", exc)
            return 0

    try:
        # Discover destination columns
        dest_cols = get_table_columns(client, table)
        if not dest_cols:
            log.error("Table %s not found in demand_planning — run create_tables.py first", table)
            return 0

        # Find intersection of source and destination columns
        src_cols = list(df.columns)
        valid_cols = [c for c in src_cols if c in dest_cols]
        missing_src = [c for c in dest_cols if c not in src_cols and "inserted_at" not in c and "updated_at" not in c]

        if missing_src:
            log.warning("Table %s: columns in dest not in source: %s — will be DEFAULT", table, missing_src)

        extra_src = [c for c in src_cols if c not in dest_cols]
        if extra_src:
            log.info("Table %s: dropping extra source columns: %s", table, extra_src)

        if not valid_cols:
            log.error("No matching columns between source and %s — skipping insert", table)
            return 0

        df_insert = df[valid_cols].copy()

        # Data type coercion for common issues
        for col in df_insert.columns:
            if df_insert[col].dtype == "object":
                df_insert[col] = df_insert[col].astype(str).replace({"nan": "", "None": ""})

        before_count = len(df_insert)
        log.info("Inserting %d rows into %s ...", before_count, table)

        client.insert_df(f"{table}", df_insert, column_names=valid_cols)

        log.info("✓ Inserted %d rows into %s", before_count, table)

        # For ReplacingMergeTree tables, run OPTIMIZE to deduplicate
        if table in REPLACING_TABLES:
            try:
                client.command(f"OPTIMIZE TABLE {table} FINAL")
                log.debug("OPTIMIZE TABLE %s FINAL — done", table)
            except Exception as exc:
                log.warning("OPTIMIZE failed for %s: %s", table, exc)

        return before_count

    except Exception as exc:
        log.error("insert_df failed for %s: %s", table, exc)
        return 0
    finally:
        if close_after:
            try:
                client.close()
            except Exception:
                pass


def log_pipeline_run(job_name: str, started_at: datetime, status: str,
                     rows_processed: int = 0, error_message: str = "",
                     client=None):
    """Write a pipeline run record to pipeline_runs table."""
    try:
        close_after = client is None
        if client is None:
            client = get_local_client()

        completed_at = datetime.now(IST)
        record = pd.DataFrame([{
            "job_name":       job_name,
            "started_at":     started_at,
            "completed_at":   completed_at,
            "status":         status,
            "rows_processed": rows_processed,
            "error_message":  error_message[:1000] if error_message else "",
        }])
        client.insert_df("pipeline_runs", record)

        if close_after:
            client.close()
    except Exception as exc:
        log.warning("Could not write pipeline run log: %s", exc)


def query_df(sql: str, client=None) -> pd.DataFrame:
    """Execute a SQL query and return a DataFrame."""
    close_after = client is None
    if client is None:
        client = get_local_client()
    try:
        return client.query_df(sql)
    except Exception as exc:
        log.error("Query failed: %s\nSQL: %s", exc, sql[:200])
        return pd.DataFrame()
    finally:
        if close_after:
            try:
                client.close()
            except Exception:
                pass

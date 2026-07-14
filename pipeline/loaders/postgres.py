"""
pipeline/loaders/postgres.py
─────────────────────────────
PostgreSQL loader — replaces the old ClickHouse loader.
Inserts DataFrames into the PostgreSQL demand_planning database.

Drop-in replacement for pipeline/loaders/clickhouse.py —
all function signatures are identical so engines need only
change their import line.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


# ── Connection ────────────────────────────────────────────────────────────────

def get_local_client():
    """Return a PostgreSQL connection (same DB the backend uses)."""
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "103.172.150.31"),
        user=os.getenv("PG_USER", "new_user"),
        password=os.getenv("PG_PASS", "StrongPassword123!"),
        dbname=os.getenv("PG_DB", "demand_planning"),
        port=int(os.getenv("PG_PORT", "5432")),
        connect_timeout=15,
    )


# ── Insert helper ─────────────────────────────────────────────────────────────

def insert_df(df: pd.DataFrame, table: str, client=None) -> int:
    """
    Truncate <table> and bulk-insert the DataFrame into PostgreSQL.
    Returns number of rows inserted.
    """
    if df is None or df.empty:
        log.info("insert_df: empty DataFrame for %s — skipping", table)
        return 0

    close_after = client is None
    if client is None:
        try:
            client = get_local_client()
        except Exception as exc:
            log.error("Cannot connect to PostgreSQL: %s", exc)
            return 0

    try:
        with client.cursor() as cur:
            # Check which columns actually exist in the table
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table,))
            dest_cols = [row[0] for row in cur.fetchall()]

            if not dest_cols:
                log.warning("Table %s not found in PostgreSQL — skipping", table)
                return 0

            # Keep only columns that exist in both source and destination
            valid_cols = [c for c in df.columns if c in dest_cols]
            if not valid_cols:
                log.error("No matching columns between source and %s — skipping", table)
                return 0

            df_insert = df[valid_cols].copy()

            # Convert NaN to None for SQL NULL
            df_insert = df_insert.where(pd.notnull(df_insert), None)

            # Truncate old data, then bulk insert fresh data
            cur.execute(f"TRUNCATE TABLE {table}")

            rows = [tuple(row) for row in df_insert.itertuples(index=False, name=None)]
            cols_sql = ", ".join(f'"{c}"' for c in valid_cols)
            insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES %s"

            psycopg2.extras.execute_values(cur, insert_sql, rows, page_size=500)
            client.commit()

        log.info("✓ Inserted %d rows into %s", len(df_insert), table)
        return len(df_insert)

    except Exception as exc:
        log.error("insert_df failed for %s: %s", table, exc)
        try:
            client.rollback()
        except Exception:
            pass
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
        with client.cursor() as cur:
            cur.execute("""
                INSERT INTO pipeline_runs
                    (job_name, started_at, completed_at, status, rows_processed, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                job_name,
                started_at,
                completed_at,
                status,
                rows_processed,
                (error_message or "")[:1000],
            ))
            client.commit()

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
        return pd.read_sql_query(sql, client)
    except Exception as exc:
        log.error("Query failed: %s\nSQL: %s", exc, sql[:200])
        return pd.DataFrame()
    finally:
        if close_after:
            try:
                client.close()
            except Exception:
                pass

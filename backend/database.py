"""
backend/database.py
────────────────────
PostgreSQL connection manager for the FastAPI backend.
"""

import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

PG_HOST = "103.172.150.31"
PG_USER = "new_user"
PG_PASS = "StrongPassword123!"
PG_DB = "demand_planning"
PG_PORT = 5432

def get_db_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(
        host=PG_HOST,
        user=PG_USER,
        password=PG_PASS,
        dbname=PG_DB,
        port=PG_PORT
    )

@contextmanager
def get_db():
    """Context manager that yields a PostgreSQL connection and ensures it's closed."""
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def query_df(sql: str, params: tuple = None):
    """Execute a SQL query and return a pandas DataFrame."""
    import pandas as pd
    with get_db() as conn:
        try:
            # pandas read_sql handles the connection object directly
            return pd.read_sql_query(sql, conn, params=params)
        except Exception as exc:
            log.error("DB query failed: %s\nSQL: %s", exc, sql[:300])
            return pd.DataFrame()


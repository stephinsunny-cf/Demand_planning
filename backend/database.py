"""
backend/database.py
────────────────────
PostgreSQL connection pool for the FastAPI backend.
Uses a ThreadedConnectionPool so connections are reused across requests
instead of being opened/closed on every call (which was causing slow loads).
"""

import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

PG_HOST = os.getenv("PG_HOST", "103.172.150.31")
PG_USER = os.getenv("PG_USER", "new_user")
PG_PASS = os.getenv("PG_PASS", "StrongPassword123!")
PG_DB   = os.getenv("PG_DB",   "demand_planning")
PG_PORT = int(os.getenv("PG_PORT", "5432"))

# Create a pool of 2–8 persistent connections at startup
_pool: pool.ThreadedConnectionPool | None = None

def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=8,
            host=PG_HOST,
            user=PG_USER,
            password=PG_PASS,
            dbname=PG_DB,
            port=PG_PORT,
            connect_timeout=10,
        )
        log.info("DB connection pool created (%s:%s/%s)", PG_HOST, PG_PORT, PG_DB)
    return _pool

@contextmanager
def get_db():
    """Yield a connection from the pool; return it when done."""
    conn = None
    p = _get_pool()
    try:
        conn = p.getconn()
        conn.autocommit = False
        yield conn
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            try:
                conn.reset()
            except Exception:
                pass
            p.putconn(conn)

def get_db_connection():
    """Legacy helper — returns a pooled connection (caller must close/return it)."""
    return _get_pool().getconn()

def query_df(sql: str, params: tuple = None):
    import pandas as pd
    import numpy as np
    with get_db() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
        df = df.replace([np.inf, -np.inf], np.nan)
        return df.where(pd.notnull(df), None)

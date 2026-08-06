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

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_USER = os.getenv("PG_USER", "new_user")
PG_PASS = os.getenv("PG_PASS", "")
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

def close_all_connections():
    """Explicitly tear down the global connection pool."""
    global _pool
    if _pool and not _pool.closed:
        try:
            _pool.closeall()
        except Exception as e:
            log.warning("Error closing connection pool: %s", e)
        _pool = None

@contextmanager
def get_db():
    """Yield a connection from the pool; return it when done."""
    global _pool
    conn = None
    p = _get_pool()
    try:
        conn = p.getconn()
        
        # Liveness check: verify connection hasn't been killed by the host (e.g. Render idle timeout)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.rollback() # end the implicit transaction from the ping
        except Exception:
            log.warning("Pooled connection dead. Rebuilding entire pool...")
            try:
                p.putconn(conn, close=True) # Explicitly discard, don't recycle
            except Exception:
                pass
            close_all_connections()         # Whole pool likely stale together — rebuild it
            p = _get_pool()
            conn = p.getconn()

        conn.autocommit = False
        yield conn
    except Exception:
        if conn and p and not p.closed:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn and p and not p.closed:
            try:
                conn.reset()
                p.putconn(conn)
            except Exception:
                # If reset fails, the connection is dirty/broken. Discard it.
                try:
                    p.putconn(conn, close=True)
                except Exception:
                    pass

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

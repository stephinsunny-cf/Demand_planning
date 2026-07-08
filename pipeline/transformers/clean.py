"""
pipeline/transformers/clean.py
───────────────────────────────
Data cleaning, deduplication, standardisation, and validation.

Business rules enforced here:
  1. Only completed/delivered orders (never cancelled/pending/failed)
  2. Remove rows with zero or negative quantities
  3. Strip whitespace from all string columns
  4. Convert all timestamps to IST
  5. Remove exact duplicate rows
  6. Flag SKUs in orders not in menu_items
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

CANCELLED_STATUSES = {"cancelled", "cancel", "failed", "failure", "pending", "rejected",
                      "refunded", "void", "voided", "abandoned"}
COMPLETED_STATUSES = {"completed", "delivered", "complete", "fulfilled", "done", "success"}


# ── Generic helpers ───────────────────────────────────────────────────────────

def strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from all string columns."""
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        # Replace literal "nan" / "None" with empty string
        df[col] = df[col].replace({"nan": "", "None": "", "NaN": ""})
    return df


def lowercase_sku(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Lowercase and strip a SKU-like column for standardisation."""
    if col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r"\s+", " ", regex=True)
        )
    return df


def to_ist(dt) -> Optional[datetime]:
    """Convert a datetime-like value to IST-aware datetime."""
    if pd.isna(dt) or dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
        except Exception:
            return None
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST)
    return None


def normalise_timestamps(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    """Convert timestamp columns to IST datetime."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            df[col] = df[col].dt.tz_convert(IST)
    return df


# ── Orders cleaning ───────────────────────────────────────────────────────────

def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Clean orders DataFrame — enforce business rules on order status."""
    if df.empty:
        return df

    original_len = len(df)
    df = strip_strings(df)

    # Rule 1: Only completed orders
    if "status" in df.columns:
        df = df[df["status"].str.lower().isin(COMPLETED_STATUSES)]
        log.info("Orders after status filter: %d / %d", len(df), original_len)

    # Rule 2: Timestamps to IST
    df = normalise_timestamps(df, "created_at")

    # Remove duplicates
    if "order_id" in df.columns:
        df = df.drop_duplicates(subset=["order_id"], keep="last")

    # Remove rows with empty order_id
    if "order_id" in df.columns:
        df = df[df["order_id"].astype(str).str.strip() != ""]

    log.info("Cleaned orders: %d rows", len(df))
    return df.reset_index(drop=True)


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    """Clean order items — remove zero/negative quantities."""
    if df.empty:
        return df

    df = strip_strings(df)
    df = normalise_timestamps(df, "created_at")

    # Rule 2: Remove zero or negative quantities
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        before = len(df)
        df = df[df["quantity"] > 0]
        log.info("Order items: removed %d rows with qty <= 0", before - len(df))

    # Standardise item name
    df = lowercase_sku(df, "item_name")

    # Deduplicate by id
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="last")

    log.info("Cleaned order items: %d rows", len(df))
    return df.reset_index(drop=True)


def clean_menu_items(df: pd.DataFrame) -> pd.DataFrame:
    """Clean menu items master."""
    if df.empty:
        return df

    df = strip_strings(df)

    # Standardise name
    df = lowercase_sku(df, "name")

    # active column — coerce to 0/1
    if "active" in df.columns:
        df["active"] = pd.to_numeric(df["active"], errors="coerce").fillna(0).astype(int)

    # price
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    # Deduplicate by id
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="last")

    log.info("Cleaned menu items: %d rows", len(df))
    return df.reset_index(drop=True)


def clean_recipe_master(df: pd.DataFrame) -> pd.DataFrame:
    """Clean recipe master — enforce yield factor business rule."""
    if df.empty:
        return df

    df = strip_strings(df)
    df = lowercase_sku(df, "dish_name")
    df = lowercase_sku(df, "ingredient")

    if "qty_per_portion" in df.columns:
        df["qty_per_portion"] = pd.to_numeric(df["qty_per_portion"], errors="coerce").fillna(0)
        df = df[df["qty_per_portion"] > 0]

    if "yield_factor" in df.columns:
        df["yield_factor"] = pd.to_numeric(df["yield_factor"], errors="coerce").fillna(1.0)
        # Yield factor must be between 0 (exclusive) and 1 (inclusive)
        df["yield_factor"] = df["yield_factor"].clip(lower=0.01, upper=1.0)
    else:
        df["yield_factor"] = 1.0

    df = df.drop_duplicates(subset=["dish_name", "ingredient"], keep="last")
    log.info("Cleaned recipe master: %d rows", len(df))
    return df.reset_index(drop=True)


# ── SupplyNote data cleaning ──────────────────────────────────────────────────

def clean_kitchen_stock(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = strip_strings(df)
    if "qty_available" in df.columns:
        df["qty_available"] = pd.to_numeric(df["qty_available"], errors="coerce").fillna(0)
        df = df[df["qty_available"] >= 0]
    return df.reset_index(drop=True)


def clean_warehouse_stock(df: pd.DataFrame) -> pd.DataFrame:
    return clean_kitchen_stock(df)  # Same logic


def clean_open_pos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = strip_strings(df)
    if "qty_ordered" in df.columns:
        df["qty_ordered"] = pd.to_numeric(df["qty_ordered"], errors="coerce").fillna(0)
    if "expected_date" in df.columns:
        df["expected_date"] = pd.to_datetime(df["expected_date"], errors="coerce").dt.date
    df = df.drop_duplicates(subset=["po_number", "ingredient"], keep="last")
    return df.reset_index(drop=True)


def clean_grn_log(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = strip_strings(df)
    for col in ["qty_ordered", "qty_received"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "received_date" in df.columns:
        df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce").dt.date
    return df.reset_index(drop=True)


def clean_vendor_master(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = strip_strings(df)
    if "lead_time_days" in df.columns:
        df["lead_time_days"] = pd.to_numeric(df["lead_time_days"], errors="coerce").fillna(3).astype(int)
    if "moq" in df.columns:
        df["moq"] = pd.to_numeric(df["moq"], errors="coerce").fillna(1.0)
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df = df.drop_duplicates(subset=["vendor_name", "ingredient"], keep="last")
    return df.reset_index(drop=True)


# ── Cross-table validation ────────────────────────────────────────────────────

def flag_unmapped_skus(orders_df: pd.DataFrame, menu_df: pd.DataFrame) -> list[str]:
    """
    Return list of SKU names appearing in order_items but NOT in menu_items.
    These will trigger INFO alerts.
    """
    if orders_df.empty or menu_df.empty:
        return []
    order_skus = set(orders_df["item_name"].dropna().unique()) if "item_name" in orders_df.columns else set()
    menu_skus  = set(menu_df["name"].dropna().unique()) if "name" in menu_df.columns else set()
    unmapped = order_skus - menu_skus
    if unmapped:
        log.warning("Found %d SKUs in orders not in menu_items: %s",
                    len(unmapped), list(unmapped)[:10])
    return list(unmapped)

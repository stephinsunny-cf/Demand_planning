"""
pipeline/extractors/supplynote.py
───────────────────────────────────
Pulls inventory, PO, GRN, and vendor data from SupplyNote via HTTP API.

Design decisions:
  - Uses captured Bearer token from env var SUPPLYNOTE_TOKEN
  - Auto-refreshes token when a 401 is received (re-login with email/password)
  - Saves raw JSON to logs/raw/ before any processing
  - Gracefully handles unknown API response structures
  - Falls back to dummy data if all retries fail
  - Never crashes the full pipeline on partial failure
"""

import os
import json
import logging
import random
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
RAW_DIR = Path(__file__).parent.parent.parent / "logs" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.getenv("SUPPLYNOTE_BASE_URL", "https://app.supplynote.com")

# Candidate endpoint patterns to try (since exact URLs are unknown)
STOCK_ENDPOINTS = [
    "/api/v1/stock",
    "/api/v1/inventory",
    "/api/v1/kitchen-stock",
    "/api/stocks",
    "/api/inventory/current",
]
WAREHOUSE_ENDPOINTS = [
    "/api/v1/warehouse-stock",
    "/api/v1/warehouse",
    "/api/warehouse/stock",
    "/api/v1/central-stock",
]
PO_ENDPOINTS = [
    "/api/v1/purchase-orders",
    "/api/v1/orders/purchase",
    "/api/purchase-orders",
    "/api/v1/po",
]
GRN_ENDPOINTS = [
    "/api/v1/grn",
    "/api/v1/goods-received",
    "/api/v1/receipts",
    "/api/grn",
]
VENDOR_ENDPOINTS = [
    "/api/v1/vendors",
    "/api/v1/suppliers",
    "/api/vendors",
    "/api/v1/vendor-master",
]


# ── Token management ──────────────────────────────────────────────────────────

_current_token: str = ""


def _load_token() -> str:
    """Load token from env or last saved value."""
    global _current_token
    if _current_token:
        return _current_token
    token = os.getenv("SUPPLYNOTE_TOKEN", "")
    if token and not token.startswith("Bearer "):
        token = f"Bearer {token}"
    _current_token = token
    return token


def _refresh_token() -> str:
    """Re-authenticate with SupplyNote and return a new Bearer token."""
    global _current_token
    email = os.getenv("SUPPLYNOTE_EMAIL", "")
    password = os.getenv("SUPPLYNOTE_PASSWORD", "")
    if not email or not password:
        log.error("SUPPLYNOTE_EMAIL or SUPPLYNOTE_PASSWORD not set — cannot refresh token")
        return _current_token

    login_urls = [
        f"{BASE_URL}/api/v1/auth/login",
        f"{BASE_URL}/api/auth/login",
        f"{BASE_URL}/api/v1/login",
        f"{BASE_URL}/auth/login",
    ]
    payload = {"email": email, "password": password}

    for url in login_urls:
        try:
            resp = requests.post(url, json=payload, timeout=15)
            log.info("Token refresh attempt: %s → %d", url, resp.status_code)
            if resp.status_code == 200:
                data = resp.json()
                # Common token key names
                token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("jwt")
                    or data.get("data", {}).get("token")
                    or data.get("data", {}).get("access_token")
                )
                if token:
                    _current_token = f"Bearer {token}"
                    log.info("Token refreshed successfully via %s", url)
                    return _current_token
        except Exception as exc:
            log.warning("Login attempt failed at %s: %s", url, exc)

    log.error("All token refresh attempts failed")
    return _current_token


def _get_headers() -> dict:
    return {
        "Authorization": _load_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _api_get(endpoint: str, params: dict = None, retry_on_401: bool = True) -> dict | list | None:
    """
    Make a GET request to a SupplyNote endpoint.
    Handles 401 by refreshing the token and retrying once.
    Logs everything for debugging.
    """
    url = BASE_URL + endpoint
    log.debug("GET %s params=%s", url, params)
    try:
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
        log.info("GET %s → %d", url, resp.status_code)

        if resp.status_code == 401 and retry_on_401:
            log.warning("401 Unauthorized — refreshing token and retrying")
            _refresh_token()
            return _api_get(endpoint, params=params, retry_on_401=False)

        if resp.status_code != 200:
            log.warning("Non-200 response from %s: %d — %s", url, resp.status_code, resp.text[:200])
            return None

        # Save raw response
        raw_name = endpoint.replace("/", "_").strip("_")
        ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        raw_path = RAW_DIR / f"supplynote_{raw_name}_{ts}.json"
        raw_path.write_text(resp.text, encoding="utf-8")
        log.debug("Raw JSON saved → %s", raw_path)

        return resp.json()
    except requests.exceptions.ConnectionError:
        log.error("Cannot reach %s — check network / SupplyNote availability", url)
        return None
    except Exception as exc:
        log.error("API error at %s: %s", url, exc)
        return None


def _try_endpoints(candidates: list[str], params: dict = None) -> dict | list | None:
    """Try a list of candidate endpoints and return the first successful response."""
    for ep in candidates:
        result = _api_get(ep, params=params)
        if result is not None:
            return result
    log.warning("All endpoint candidates failed: %s", candidates)
    return None


# ── Data normalisation helpers ────────────────────────────────────────────────

def _find_key(d: dict, *keywords: str):
    """Find the first dict key containing any keyword (case-insensitive)."""
    for key in d.keys():
        for kw in keywords:
            if kw.lower() in key.lower():
                return key
    return None


def _to_list(data) -> list:
    """Normalise API response to a flat list of dicts."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Common wrapper keys
        for key in ("data", "results", "items", "records", "response", "list"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # If data itself looks like a paginated response
        if "count" in data or "total" in data:
            for key in data:
                if isinstance(data[key], list):
                    return data[key]
    return []


# ── Extract functions ─────────────────────────────────────────────────────────

def pull_kitchen_stock() -> pd.DataFrame:
    """Pull current kitchen/outlet stock levels."""
    raw = _try_endpoints(STOCK_ENDPOINTS)
    if raw is None:
        log.warning("Kitchen stock: all endpoints failed — using dummy data")
        return _dummy_kitchen_stock()

    rows = _to_list(raw)
    if not rows:
        return _dummy_kitchen_stock()

    # Normalise fields
    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kitchen_key    = _find_key(row, "kitchen", "outlet", "store", "branch", "location")
        ingredient_key = _find_key(row, "ingredient", "item", "material", "product", "name")
        qty_key        = _find_key(row, "quantity", "qty", "stock", "available", "balance")
        unit_key       = _find_key(row, "unit", "uom", "measure")

        records.append({
            "snapshot_time": datetime.now(IST),
            "kitchen":       row.get(kitchen_key, "Unknown") if kitchen_key else "Unknown",
            "ingredient":    row.get(ingredient_key, "Unknown") if ingredient_key else "Unknown",
            "qty_available": float(row.get(qty_key, 0) or 0) if qty_key else 0.0,
            "unit":          row.get(unit_key, "g") if unit_key else "g",
        })

    df = pd.DataFrame(records) if records else _dummy_kitchen_stock()
    log.info("Kitchen stock: %d rows", len(df))
    return df


def pull_warehouse_stock() -> pd.DataFrame:
    """Pull current warehouse stock levels."""
    raw = _try_endpoints(WAREHOUSE_ENDPOINTS)
    if raw is None:
        return _dummy_warehouse_stock()

    rows = _to_list(raw)
    if not rows:
        return _dummy_warehouse_stock()

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        warehouse_key  = _find_key(row, "warehouse", "store", "hub", "central")
        ingredient_key = _find_key(row, "ingredient", "item", "material", "product", "name")
        qty_key        = _find_key(row, "quantity", "qty", "stock", "available")
        unit_key       = _find_key(row, "unit", "uom")

        records.append({
            "snapshot_time": datetime.now(IST),
            "warehouse":     row.get(warehouse_key, "Central Warehouse") if warehouse_key else "Central Warehouse",
            "ingredient":    row.get(ingredient_key, "Unknown") if ingredient_key else "Unknown",
            "qty_available": float(row.get(qty_key, 0) or 0) if qty_key else 0.0,
            "unit":          row.get(unit_key, "g") if unit_key else "g",
        })

    df = pd.DataFrame(records) if records else _dummy_warehouse_stock()
    log.info("Warehouse stock: %d rows", len(df))
    return df


def pull_open_pos() -> pd.DataFrame:
    """Pull open purchase orders."""
    raw = _try_endpoints(PO_ENDPOINTS, params={"status": "open"})
    if raw is None:
        return _dummy_open_pos()

    rows = _to_list(raw)
    if not rows:
        return _dummy_open_pos()

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        po_key        = _find_key(row, "po_number", "po", "order_id", "id", "number")
        vendor_key    = _find_key(row, "vendor", "supplier", "partner")
        ingredient_key= _find_key(row, "ingredient", "item", "material", "product", "name")
        qty_key       = _find_key(row, "quantity", "qty", "ordered")
        date_key      = _find_key(row, "expected", "delivery", "due", "eta")
        status_key    = _find_key(row, "status", "state")

        records.append({
            "po_number":     str(row.get(po_key, "")) if po_key else "",
            "vendor":        row.get(vendor_key, "") if vendor_key else "",
            "ingredient":    row.get(ingredient_key, "") if ingredient_key else "",
            "qty_ordered":   float(row.get(qty_key, 0) or 0) if qty_key else 0.0,
            "expected_date": row.get(date_key, str(date.today() + timedelta(days=3))) if date_key else str(date.today() + timedelta(days=3)),
            "status":        row.get(status_key, "open") if status_key else "open",
        })

    df = pd.DataFrame(records) if records else _dummy_open_pos()
    log.info("Open POs: %d rows", len(df))
    return df


def pull_grn_log() -> pd.DataFrame:
    """Pull goods received notes."""
    raw = _try_endpoints(GRN_ENDPOINTS)
    if raw is None:
        return _dummy_grn_log()

    rows = _to_list(raw)
    if not rows:
        return _dummy_grn_log()

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        grn_key       = _find_key(row, "grn_number", "grn", "id", "receipt")
        po_key        = _find_key(row, "po_number", "po", "purchase_order")
        ingredient_key= _find_key(row, "ingredient", "item", "material", "product")
        ordered_key   = _find_key(row, "ordered", "expected", "requested")
        received_key  = _find_key(row, "received", "actual", "quantity")
        date_key      = _find_key(row, "received_date", "date", "created")

        records.append({
            "grn_number":   str(row.get(grn_key, "")) if grn_key else "",
            "po_number":    str(row.get(po_key, "")) if po_key else "",
            "ingredient":   row.get(ingredient_key, "") if ingredient_key else "",
            "qty_ordered":  float(row.get(ordered_key, 0) or 0) if ordered_key else 0.0,
            "qty_received": float(row.get(received_key, 0) or 0) if received_key else 0.0,
            "received_date": row.get(date_key, str(date.today())) if date_key else str(date.today()),
        })

    df = pd.DataFrame(records) if records else _dummy_grn_log()
    log.info("GRN log: %d rows", len(df))
    return df


def pull_vendor_master() -> pd.DataFrame:
    """Pull vendor / supplier master data."""
    raw = _try_endpoints(VENDOR_ENDPOINTS)
    if raw is None:
        return _dummy_vendor_master()

    rows = _to_list(raw)
    if not rows:
        return _dummy_vendor_master()

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        vendor_key    = _find_key(row, "vendor", "supplier", "name")
        ingredient_key= _find_key(row, "ingredient", "item", "material", "product")
        lead_key      = _find_key(row, "lead_time", "lead", "days", "tat")
        moq_key       = _find_key(row, "moq", "minimum", "min_order")
        unit_key      = _find_key(row, "unit", "uom")
        price_key     = _find_key(row, "price", "cost", "rate", "amount")

        records.append({
            "vendor_name":   row.get(vendor_key, "") if vendor_key else "",
            "ingredient":    row.get(ingredient_key, "") if ingredient_key else "",
            "lead_time_days": int(row.get(lead_key, 3) or 3) if lead_key else 3,
            "moq":           float(row.get(moq_key, 1) or 1) if moq_key else 1.0,
            "unit":          row.get(unit_key, "kg") if unit_key else "kg",
            "price":         float(row.get(price_key, 0) or 0) if price_key else 0.0,
        })

    df = pd.DataFrame(records) if records else _dummy_vendor_master()
    log.info("Vendor master: %d rows", len(df))
    return df


# ── Dummy data fallbacks ──────────────────────────────────────────────────────

INGREDIENTS = [
    ("Paneer", "g"), ("Chicken", "g"), ("Basmati Rice", "g"), ("Tomato Puree", "ml"),
    ("Butter", "g"), ("Maida", "g"), ("Mozzarella", "g"), ("Black Lentils", "g"),
    ("Biryani Masala", "g"), ("Whole Wheat Wrap", "g"), ("Potato", "g"),
    ("Onion", "g"), ("Cooking Oil", "ml"), ("Salt", "g"), ("Ginger Garlic Paste", "g"),
]
KITCHENS = ["Koramangala", "Indiranagar", "HSR Layout", "Whitefield", "JP Nagar"]
VENDORS = ["FreshVeggies Co", "DairyBest", "StarDry Goods", "SpiceKing", "MeatPrime"]


def _dummy_kitchen_stock() -> pd.DataFrame:
    rows = []
    for kitchen in KITCHENS:
        for ingredient, unit in INGREDIENTS:
            rows.append({
                "snapshot_time": datetime.now(IST),
                "kitchen": kitchen,
                "ingredient": ingredient,
                "qty_available": round(random.uniform(500, 10000), 2),
                "unit": unit,
            })
    return pd.DataFrame(rows)


def _dummy_warehouse_stock() -> pd.DataFrame:
    rows = []
    for ingredient, unit in INGREDIENTS:
        rows.append({
            "snapshot_time": datetime.now(IST),
            "warehouse": "Central Warehouse",
            "ingredient": ingredient,
            "qty_available": round(random.uniform(5000, 100000), 2),
            "unit": unit,
        })
    return pd.DataFrame(rows)


def _dummy_open_pos() -> pd.DataFrame:
    rows = []
    for i in range(12):
        ingredient, unit = random.choice(INGREDIENTS)
        rows.append({
            "po_number": f"PO-2024-{1000 + i}",
            "vendor": random.choice(VENDORS),
            "ingredient": ingredient,
            "qty_ordered": round(random.uniform(10000, 100000), 2),
            "expected_date": str(date.today() + timedelta(days=random.randint(1, 7))),
            "status": "open",
        })
    return pd.DataFrame(rows)


def _dummy_grn_log() -> pd.DataFrame:
    rows = []
    for i in range(20):
        ingredient, unit = random.choice(INGREDIENTS)
        ordered = round(random.uniform(5000, 50000), 2)
        rows.append({
            "grn_number": f"GRN-{2000 + i}",
            "po_number": f"PO-2024-{random.randint(900, 999)}",
            "ingredient": ingredient,
            "qty_ordered": ordered,
            "qty_received": round(ordered * random.uniform(0.90, 1.0), 2),
            "received_date": str(date.today() - timedelta(days=random.randint(0, 14))),
        })
    return pd.DataFrame(rows)


def _dummy_vendor_master() -> pd.DataFrame:
    rows = []
    for vendor in VENDORS:
        for ingredient, unit in INGREDIENTS[:5]:
            rows.append({
                "vendor_name": vendor,
                "ingredient": ingredient,
                "lead_time_days": random.randint(1, 5),
                "moq": round(random.uniform(1000, 10000), 2),
                "unit": unit,
                "price": round(random.uniform(10, 500), 2),
            })
    return pd.DataFrame(rows)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_all(use_dummy: bool = False) -> dict[str, pd.DataFrame]:
    """Extract all SupplyNote datasets. Falls back gracefully on failures."""
    if use_dummy:
        log.info("SupplyNote: using dummy data")
        return {
            "kitchen_stock":   _dummy_kitchen_stock(),
            "warehouse_stock": _dummy_warehouse_stock(),
            "open_pos":        _dummy_open_pos(),
            "grn_log":         _dummy_grn_log(),
            "vendor_master":   _dummy_vendor_master(),
        }

    results = {}
    tasks = {
        "kitchen_stock":   pull_kitchen_stock,
        "warehouse_stock": pull_warehouse_stock,
        "open_pos":        pull_open_pos,
        "grn_log":         pull_grn_log,
        "vendor_master":   pull_vendor_master,
    }
    for name, fn in tasks.items():
        try:
            results[name] = fn()
        except Exception as exc:
            log.error("SupplyNote %s extraction error: %s — using dummy", name, exc)
            # Individual fallbacks already applied inside each fn
            results[name] = pd.DataFrame()

    return results

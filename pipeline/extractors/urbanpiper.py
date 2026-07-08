"""
pipeline/extractors/urbanpiper.py
──────────────────────────────────
Pulls order data from the UrbanPiper ClickHouse database.

Key design decisions:
  - Discovers actual column names at runtime via DESCRIBE TABLE
    because exact column names are not known in advance.
  - Falls back to dummy data if the connection fails.
  - Saves raw CSV to logs/raw/ before any transformation.
  - Only pulls completed / delivered orders (never cancelled / pending).
"""

import os
import logging
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

log = logging.getLogger(__name__)

# IST offset
IST = timezone(timedelta(hours=5, minutes=30))

# Raw dump directory
RAW_DIR = Path(__file__).parent.parent.parent / "logs" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# ── Connection ────────────────────────────────────────────────────────────────

def _get_source_client():
    """Create and return a ClickHouse client for UrbanPiper."""
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=os.getenv("SOURCE_HOST", "cfi-data-secure.urbanpiper.com"),
        port=int(os.getenv("SOURCE_PORT", 8123)),
        username=os.getenv("SOURCE_USER", "curefoods"),
        password=os.getenv("SOURCE_PASSWORD", ""),
        database="urbanpiper",
        secure=True,
        connect_timeout=30,
        send_receive_timeout=120,
    )


def test_connection() -> bool:
    """Test whether the UrbanPiper ClickHouse is reachable."""
    try:
        client = _get_source_client()
        client.query("SELECT 1")
        client.close()
        log.info("UrbanPiper connection: OK")
        return True
    except Exception as exc:
        log.warning(
            "UrbanPiper connection failed: %s\n"
            "TIP: If you are on office WiFi, try switching to a mobile hotspot.",
            exc,
        )
        return False


# ── Schema discovery ─────────────────────────────────────────────────────────

def discover_columns(client, table_name: str) -> list[str]:
    """Run DESCRIBE TABLE and return list of column names."""
    try:
        result = client.query(f"DESCRIBE TABLE {table_name}")
        cols = [row[0] for row in result.result_rows]
        log.info("Discovered columns for %s: %s", table_name, cols)
        return cols
    except Exception as exc:
        log.error("Could not describe table %s: %s", table_name, exc)
        return []


def _find_column(candidates: list[str], *keywords: str) -> Optional[str]:
    """Return the first column name that contains any of the given keywords."""
    for col in candidates:
        for kw in keywords:
            if kw.lower() in col.lower():
                return col
    return None


# ── Raw data save ─────────────────────────────────────────────────────────────

def _save_raw(df: pd.DataFrame, name: str):
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    path = RAW_DIR / f"{name}_{ts}.csv"
    df.to_csv(path, index=False)
    log.info("Raw data saved → %s (%d rows)", path, len(df))


# ── Extraction functions ──────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def pull_orders(client, days: int = 90) -> pd.DataFrame:
    """Pull completed orders from UrbanPiper (last N days)."""
    cols = discover_columns(client, "orders")

    # Discover key column names dynamically
    status_col  = _find_column(cols, "status")
    created_col = _find_column(cols, "created_at", "created", "timestamp", "date")
    store_col   = _find_column(cols, "store", "outlet", "kitchen", "branch")
    brand_col   = _find_column(cols, "brand")
    total_col   = _find_column(cols, "total", "amount", "revenue", "price")
    id_col      = _find_column(cols, "id", "order_id", "uuid")
    city_col    = _find_column(cols, "city", "location", "region")

    log.info(
        "orders column mapping → id=%s status=%s created=%s store=%s brand=%s total=%s city=%s",
        id_col, status_col, created_col, store_col, brand_col, total_col, city_col,
    )

    query = f"""
        SELECT *
        FROM orders
        WHERE {created_col} >= today() - {days}
        LIMIT 500000
    """

    df = client.query_df(query)
    log.info("Pulled %d raw orders from UrbanPiper", len(df))
    _save_raw(df, "orders_raw")

    # Filter completed/delivered only
    if status_col and status_col in df.columns:
        completed_statuses = {"completed", "delivered", "complete", "fulfilled"}
        df = df[df[status_col].str.lower().str.strip().isin(completed_statuses)]
        log.info("%d orders remaining after status filter", len(df))

    # Normalise column names
    rename_map = {}
    if id_col:      rename_map[id_col]      = "order_id"
    if created_col: rename_map[created_col] = "created_at"
    if store_col:   rename_map[store_col]   = "store_name"
    if brand_col:   rename_map[brand_col]   = "brand"
    if status_col:  rename_map[status_col]  = "status"
    if total_col:   rename_map[total_col]   = "total"
    if city_col:    rename_map[city_col]    = "city"

    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    for req in ["order_id", "created_at", "store_name", "brand", "status", "total", "city"]:
        if req not in df.columns:
            df[req] = ""

    return df[["order_id", "created_at", "store_name", "brand", "status", "total", "city"]]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def pull_order_items(client, days: int = 90) -> pd.DataFrame:
    """Pull order line items from UrbanPiper (last N days)."""
    cols = discover_columns(client, "order_items")

    id_col       = _find_column(cols, "id")
    order_id_col = _find_column(cols, "order_id", "order")
    item_col     = _find_column(cols, "item_name", "dish", "name", "product")
    qty_col      = _find_column(cols, "quantity", "qty", "count")
    price_col    = _find_column(cols, "price", "amount", "cost")
    created_col  = _find_column(cols, "created_at", "created", "timestamp")

    query = f"""
        SELECT *
        FROM order_items
        WHERE {created_col} >= today() - {days}
        LIMIT 2000000
    """
    df = client.query_df(query)
    log.info("Pulled %d raw order items", len(df))
    _save_raw(df, "order_items_raw")

    rename_map = {}
    if id_col:       rename_map[id_col]       = "id"
    if order_id_col: rename_map[order_id_col] = "order_id"
    if item_col:     rename_map[item_col]     = "item_name"
    if qty_col:      rename_map[qty_col]      = "quantity"
    if price_col:    rename_map[price_col]    = "price"
    if created_col:  rename_map[created_col]  = "created_at"
    df = df.rename(columns=rename_map)

    for req in ["id", "order_id", "item_name", "quantity", "price", "created_at"]:
        if req not in df.columns:
            df[req] = None

    return df[["id", "order_id", "item_name", "quantity", "price", "created_at"]]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def pull_menu_items(client) -> pd.DataFrame:
    """Pull full menu items master table."""
    cols = discover_columns(client, "menu_items")

    id_col       = _find_column(cols, "id")
    name_col     = _find_column(cols, "name", "dish", "item", "title")
    brand_col    = _find_column(cols, "brand")
    category_col = _find_column(cols, "category", "cat", "type")
    price_col    = _find_column(cols, "price", "cost", "amount")
    active_col   = _find_column(cols, "active", "enabled", "status", "available")

    df = client.query_df("SELECT * FROM menu_items LIMIT 100000")
    log.info("Pulled %d menu items", len(df))
    _save_raw(df, "menu_items_raw")

    rename_map = {}
    if id_col:       rename_map[id_col]       = "id"
    if name_col:     rename_map[name_col]     = "name"
    if brand_col:    rename_map[brand_col]    = "brand"
    if category_col: rename_map[category_col] = "category"
    if price_col:    rename_map[price_col]    = "price"
    if active_col:   rename_map[active_col]   = "active"
    df = df.rename(columns=rename_map)

    for req in ["id", "name", "brand", "category", "price", "active"]:
        if req not in df.columns:
            df[req] = None

    return df[["id", "name", "brand", "category", "price", "active"]]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def pull_recipe_master(client) -> pd.DataFrame:
    """Pull dishes_ingredient_breakup (recipe master) table."""
    cols = discover_columns(client, "dishes_ingredient_breakup")

    dish_col       = _find_column(cols, "dish", "item", "name", "product")
    ingredient_col = _find_column(cols, "ingredient", "material", "raw")
    qty_col        = _find_column(cols, "quantity", "qty", "amount")
    unit_col       = _find_column(cols, "unit", "uom", "measure")
    yield_col      = _find_column(cols, "yield", "factor", "ratio")

    df = client.query_df("SELECT * FROM dishes_ingredient_breakup LIMIT 200000")
    log.info("Pulled %d recipe rows", len(df))
    _save_raw(df, "recipe_master_raw")

    rename_map = {}
    if dish_col:       rename_map[dish_col]       = "dish_name"
    if ingredient_col: rename_map[ingredient_col] = "ingredient"
    if qty_col:        rename_map[qty_col]        = "qty_per_portion"
    if unit_col:       rename_map[unit_col]       = "unit"
    if yield_col:      rename_map[yield_col]      = "yield_factor"
    df = df.rename(columns=rename_map)

    for req in ["dish_name", "ingredient", "qty_per_portion", "unit"]:
        if req not in df.columns:
            df[req] = None
    if "yield_factor" not in df.columns:
        df["yield_factor"] = 1.0

    return df[["dish_name", "ingredient", "qty_per_portion", "unit", "yield_factor"]]


# ── Dummy data fallback ───────────────────────────────────────────────────────

def _generate_dummy_orders(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate realistic dummy orders and order_items for offline development."""
    import random
    from datetime import date

    brands = ["EatFit", "Yumlane", "Aligarh House", "Nomad Pizza", "Sharief Bhai"]
    outlets = ["Koramangala", "Indiranagar", "HSR Layout", "Whitefield", "JP Nagar"]
    cities = ["Bangalore", "Hyderabad", "Mumbai", "Chennai", "Pune"]
    dishes = [
        "Paneer Butter Masala", "Chicken Biryani", "Veg Biryani", "Dal Makhani",
        "Butter Naan", "Chicken Tikka", "Grilled Sandwich", "Pizza Margherita",
        "Pasta Arrabbiata", "Fruit Bowl", "Protein Wrap", "Masala Dosa",
    ]

    orders = []
    items = []
    start = datetime.now(IST) - timedelta(days=days)

    order_id = 1000
    item_id = 5000

    for day_offset in range(days):
        day = start + timedelta(days=day_offset)
        daily_orders = random.randint(40, 120)
        for _ in range(daily_orders):
            o_id = str(order_id)
            outlet = random.choice(outlets)
            brand = random.choice(brands)
            city = random.choice(cities)
            ts = day + timedelta(hours=random.randint(10, 22), minutes=random.randint(0, 59))
            num_items = random.randint(1, 4)
            order_total = 0.0
            for _ in range(num_items):
                dish = random.choice(dishes)
                qty = random.randint(1, 3)
                price = round(random.uniform(80, 450), 2)
                order_total += qty * price
                items.append({
                    "id": str(item_id),
                    "order_id": o_id,
                    "item_name": dish,
                    "quantity": qty,
                    "price": price,
                    "created_at": ts,
                })
                item_id += 1

            orders.append({
                "order_id": o_id,
                "created_at": ts,
                "store_name": outlet,
                "brand": brand,
                "status": "completed",
                "total": round(order_total, 2),
                "city": city,
            })
            order_id += 1

    return pd.DataFrame(orders), pd.DataFrame(items)


def _generate_dummy_menu() -> pd.DataFrame:
    brands = ["EatFit", "Yumlane", "Aligarh House", "Nomad Pizza", "Sharief Bhai"]
    dishes = [
        ("Paneer Butter Masala", "Main Course", 280),
        ("Chicken Biryani", "Biryani", 320),
        ("Veg Biryani", "Biryani", 250),
        ("Dal Makhani", "Main Course", 220),
        ("Butter Naan", "Bread", 45),
        ("Chicken Tikka", "Starter", 380),
        ("Grilled Sandwich", "Snacks", 150),
        ("Pizza Margherita", "Pizza", 299),
        ("Pasta Arrabbiata", "Pasta", 249),
        ("Fruit Bowl", "Healthy", 180),
        ("Protein Wrap", "Healthy", 220),
        ("Masala Dosa", "South Indian", 130),
    ]
    rows = []
    for i, (name, cat, price) in enumerate(dishes):
        for brand in brands:
            rows.append({
                "id": f"menu_{i}_{brand[:3].lower()}",
                "name": name,
                "brand": brand,
                "category": cat,
                "price": float(price),
                "active": 1,
            })
    return pd.DataFrame(rows)


def _generate_dummy_recipes() -> pd.DataFrame:
    recipes = [
        ("Paneer Butter Masala", "Paneer", 200, "g", 0.95),
        ("Paneer Butter Masala", "Tomato Puree", 100, "ml", 1.0),
        ("Paneer Butter Masala", "Butter", 30, "g", 1.0),
        ("Chicken Biryani", "Chicken", 300, "g", 0.78),
        ("Chicken Biryani", "Basmati Rice", 200, "g", 0.90),
        ("Chicken Biryani", "Biryani Masala", 15, "g", 1.0),
        ("Veg Biryani", "Mixed Vegetables", 250, "g", 0.85),
        ("Veg Biryani", "Basmati Rice", 200, "g", 0.90),
        ("Dal Makhani", "Black Lentils", 150, "g", 0.92),
        ("Dal Makhani", "Butter", 40, "g", 1.0),
        ("Butter Naan", "Maida", 100, "g", 0.95),
        ("Butter Naan", "Butter", 20, "g", 1.0),
        ("Chicken Tikka", "Chicken", 250, "g", 0.78),
        ("Chicken Tikka", "Tikka Marinade", 50, "ml", 1.0),
        ("Pizza Margherita", "Pizza Dough", 200, "g", 0.95),
        ("Pizza Margherita", "Tomato Sauce", 80, "ml", 1.0),
        ("Pizza Margherita", "Mozzarella", 100, "g", 1.0),
        ("Protein Wrap", "Chicken Breast", 200, "g", 0.82),
        ("Protein Wrap", "Whole Wheat Wrap", 80, "g", 1.0),
        ("Masala Dosa", "Rice Batter", 200, "ml", 1.0),
        ("Masala Dosa", "Potato Filling", 150, "g", 0.90),
    ]
    return pd.DataFrame(recipes, columns=["dish_name", "ingredient", "qty_per_portion", "unit", "yield_factor"])


# ── Public API ────────────────────────────────────────────────────────────────

def extract_all(use_dummy: bool = False) -> dict[str, pd.DataFrame]:
    """
    Extract all 4 tables from UrbanPiper.
    Falls back to dummy data if use_dummy=True or connection fails.
    """
    if use_dummy:
        log.info("Using dummy data (USE_DUMMY_DATA=true)")
        orders_df, items_df = _generate_dummy_orders()
        return {
            "orders":        orders_df,
            "order_items":   items_df,
            "menu_items":    _generate_dummy_menu(),
            "recipe_master": _generate_dummy_recipes(),
        }

    if not test_connection():
        log.warning("Falling back to dummy data due to connection failure.")
        orders_df, items_df = _generate_dummy_orders()
        return {
            "orders":        orders_df,
            "order_items":   items_df,
            "menu_items":    _generate_dummy_menu(),
            "recipe_master": _generate_dummy_recipes(),
        }

    try:
        client = _get_source_client()
        result = {
            "orders":        pull_orders(client),
            "order_items":   pull_order_items(client),
            "menu_items":    pull_menu_items(client),
            "recipe_master": pull_recipe_master(client),
        }
        client.close()
        return result
    except Exception as exc:
        log.error("UrbanPiper extraction failed: %s — using dummy data", exc)
        orders_df, items_df = _generate_dummy_orders()
        return {
            "orders":        orders_df,
            "order_items":   items_df,
            "menu_items":    _generate_dummy_menu(),
            "recipe_master": _generate_dummy_recipes(),
        }

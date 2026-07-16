"""
scripts/sync_supplynote_daily.py
─────────────────────────────────
All-in-one daily sync script:
  1. Uses Playwright to log in to SupplyNote and get the S3 download URL.
  2. Downloads the CSV directly into memory (no file saved to disk).
  3. Cleans the data and upserts it into PostgreSQL.

Usage:
  python scripts/sync_supplynote_daily.py            # yesterday only (cron mode)
  python scripts/sync_supplynote_daily.py --date 2026-07-10  # specific date
"""

import os
import io
import sys
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from psycopg2.extras import execute_values

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("supplynote_sync")

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()  # loads .env locally; on GitHub Actions env vars are injected directly

SN_USERNAME  = os.getenv("SUPPLYNOTE_USER")
SN_PASSWORD  = os.getenv("SUPPLYNOTE_PASSWORD")
BUSINESS_ID  = "65b205675255c93a41dd7849"

PG_HOST = os.getenv("PG_HOST", "103.172.150.31")
PG_USER = os.getenv("PG_USER", "new_user")
PG_PASS = os.getenv("PG_PASS")
PG_DB   = os.getenv("PG_DB",   "demand_planning")
PG_PORT = int(os.getenv("PG_PORT", "5432"))


# ── Database helpers ──────────────────────────────────────────────────────────
def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=PG_HOST, user=PG_USER, password=PG_PASS,
        dbname=PG_DB, port=PG_PORT, connect_timeout=30
    )


def ensure_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_ingredients (
            sku VARCHAR PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            is_packaged VARCHAR,
            measuring_unit VARCHAR
        );
        CREATE TABLE IF NOT EXISTS dim_outlets (
            outlet VARCHAR PRIMARY KEY,
            name VARCHAR,
            city VARCHAR
        );
        CREATE TABLE IF NOT EXISTS kitchen_ingredient_mapping (
            outlet VARCHAR,
            sku    VARCHAR,
            PRIMARY KEY (outlet, sku)
        );
        CREATE TABLE IF NOT EXISTS fact_daily_sales (
            date               DATE,
            sku                VARCHAR,
            outlet             VARCHAR,
            qty_sold           NUMERIC,
            currently_available NUMERIC,
            oos                VARCHAR,
            PRIMARY KEY (date, sku, outlet)
        );
    """)


# ── Data cleaning ─────────────────────────────────────────────────────────────
def clean_dataframe(df):
    """Clean and standardise the raw SupplyNote CSV (already loaded into memory)."""

    # ── detect columns ───────────────────────────────────────────────────────
    date_col    = next((c for c in df.columns if "date"    in c.lower()), None)
    qty_col     = "plannedDemand" if "plannedDemand" in df.columns else \
                  next((c for c in df.columns if "qty" in c.lower() or "demand" in c.lower()), None)
    sku_col     = "ingredientCode"  if "ingredientCode"  in df.columns else "IngredientCode"
    sku_name_c  = "ingredientName"  if "ingredientName"  in df.columns else "IngredientName"
    cat_col     = "ingredientCategory" if "ingredientCategory" in df.columns else None
    pack_col    = "isPackaged"      if "isPackaged"      in df.columns else None
    unit_col    = "measuringUnit"   if "measuringUnit"   in df.columns else None
    outlet_col  = "kitchenCode"     if "kitchenCode"     in df.columns else "KitchenCode"
    outlet_nc   = "kitchenName"     if "kitchenName"     in df.columns else "KitchenName"
    city_col    = "city"            if "city"            in df.columns else None
    oos_col     = "oos"             if "oos"             in df.columns else None
    avail_col   = "currentlyAvailable" if "currentlyAvailable" in df.columns else None

    if not all([date_col, qty_col, sku_col, outlet_col]):
        log.error("Missing critical columns – skipping.")
        return None, {}, {}, set()

    # ── force types ──────────────────────────────────────────────────────────
    df[sku_col]    = df[sku_col].astype(str).str.strip()
    df[outlet_col] = df[outlet_col].astype(str).str.strip()
    df[qty_col]    = pd.to_numeric(df[qty_col], errors="coerce").fillna(0.0)
    if avail_col:
        df[avail_col] = pd.to_numeric(df[avail_col], errors="coerce").fillna(0.0)

    # ── build dimension dicts ─────────────────────────────────────────────────
    dim_ingredients = {}
    for _, row in df[[c for c in [sku_col, sku_name_c, cat_col, pack_col, unit_col] if c]].drop_duplicates().iterrows():
        sku = row[sku_col]
        if sku not in dim_ingredients:
            dim_ingredients[sku] = {
                "name":       row.get(sku_name_c, ""),
                "category":   row.get(cat_col, "")    if cat_col  else "",
                "isPackaged": str(row.get(pack_col, "")) if pack_col else "",
                "unit":       row.get(unit_col, "")   if unit_col else "",
            }

    dim_outlets = {}
    for _, row in df[[c for c in [outlet_col, outlet_nc, city_col] if c]].drop_duplicates().iterrows():
        outlet = row[outlet_col]
        if outlet not in dim_outlets:
            dim_outlets[outlet] = {
                "name": row.get(outlet_nc, ""),
                "city": row.get(city_col, "") if city_col else "",
            }

    mapping = set(zip(df[outlet_col], df[sku_col]))

    # ── facts: drop zero demand ───────────────────────────────────────────────
    df_facts = df[df[qty_col] != 0].copy()
    rename   = {date_col: "date", sku_col: "sku", outlet_col: "outlet", qty_col: "qty_sold"}
    if avail_col: rename[avail_col] = "currently_available"
    if oos_col:   rename[oos_col]   = "oos"
    df_facts = df_facts.rename(columns=rename)
    df_facts["date"] = pd.to_datetime(df_facts["date"], dayfirst=True, errors="coerce")

    keep = ["date", "sku", "outlet", "qty_sold"]
    if avail_col: keep.append("currently_available")
    if oos_col:   keep.append("oos")
    df_facts = df_facts[keep]

    # ── deduplicate ───────────────────────────────────────────────────────────
    agg = {"qty_sold": "sum"}
    if "currently_available" in df_facts.columns: agg["currently_available"] = "first"
    if "oos"                 in df_facts.columns: agg["oos"]                 = "first"
    df_facts = df_facts.groupby(["date", "sku", "outlet"], as_index=False).agg(agg)

    return df_facts, dim_ingredients, dim_outlets, mapping


# ── DB upsert ─────────────────────────────────────────────────────────────────
def upsert_to_db(df_facts, dim_ingredients, dim_outlets, mapping):
    conn   = get_conn()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        ensure_tables(cursor)

        # dim_ingredients
        ing_data = [(sku, d["name"], d["category"], d["isPackaged"], d["unit"])
                    for sku, d in dim_ingredients.items()]
        if ing_data:
            execute_values(cursor, """
                INSERT INTO dim_ingredients (sku, name, category, is_packaged, measuring_unit)
                VALUES %s
                ON CONFLICT (sku) DO UPDATE SET
                    name=EXCLUDED.name, category=EXCLUDED.category,
                    is_packaged=EXCLUDED.is_packaged, measuring_unit=EXCLUDED.measuring_unit
            """, ing_data)

        # dim_outlets
        out_data = [(o, d["name"], d["city"]) for o, d in dim_outlets.items()]
        if out_data:
            execute_values(cursor, """
                INSERT INTO dim_outlets (outlet, name, city) VALUES %s
                ON CONFLICT (outlet) DO UPDATE SET name=EXCLUDED.name, city=EXCLUDED.city
            """, out_data)

        # kitchen_ingredient_mapping
        if mapping:
            execute_values(cursor, """
                INSERT INTO kitchen_ingredient_mapping (outlet, sku) VALUES %s
                ON CONFLICT (outlet, sku) DO NOTHING
            """, list(mapping))

        # fact_daily_sales
        if df_facts is not None and len(df_facts) > 0:
            fact_data = []
            for _, row in df_facts.iterrows():
                if pd.isna(row["date"]): continue
                oos  = row.get("oos", None)
                avail = row.get("currently_available", 0.0)
                if pd.isna(oos): oos = None
                fact_data.append((
                    row["date"].strftime("%Y-%m-%d"),
                    row["sku"], row["outlet"],
                    row["qty_sold"], avail, oos
                ))

            if fact_data:
                execute_values(cursor, """
                    INSERT INTO fact_daily_sales (date, sku, outlet, qty_sold, currently_available, oos)
                    VALUES %s
                    ON CONFLICT (date, sku, outlet) DO UPDATE SET
                        qty_sold=EXCLUDED.qty_sold,
                        currently_available=EXCLUDED.currently_available,
                        oos=EXCLUDED.oos
                """, fact_data, page_size=10000)
                log.info(f"Upserted {len(fact_data)} fact rows into fact_daily_sales.")

        conn.commit()
        log.info("DB commit successful.")

    except Exception as e:
        conn.rollback()
        log.error(f"DB error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# ── Main orchestrator ─────────────────────────────────────────────────────────
def run():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Specific date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target = datetime.now() - timedelta(days=1)
        target = target.replace(hour=0, minute=0, second=0, microsecond=0)

    log.info(f"Syncing data for: {target.strftime('%Y-%m-%d')}")

    plan_date_utc = target.strftime("%Y-%m-%dT18:30:00.000Z")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            accept_downloads=False,
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # ── Login ────────────────────────────────────────────────────────
            log.info("Navigating to SupplyNote signin...")
            page.goto("https://www.supplynote.in/signin", wait_until="domcontentloaded", timeout=60000)
            page.fill('input[name="username"], input[name="email"], input[placeholder*="username" i], input[placeholder*="email" i]', SN_USERNAME)
            page.fill('input[type="password"]', SN_PASSWORD)
            page.click('button[type="submit"]')
            try:
                page.wait_for_url(lambda url: "/signin" not in url and "/login" not in url, timeout=25000)
                log.info("Logged in successfully!")
            except PWTimeout:
                log.error("Login failed. Check SUPPLYNOTE_USER / SUPPLYNOTE_PASSWORD secrets.")
                sys.exit(1)

            # ── Get version key ───────────────────────────────────────────────
            versions = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('/api/demandplan/history/semiFinished?business={BUSINESS_ID}&planDate={plan_date_utc}',
                        {{ headers: {{ 'Accept': 'application/json' }} }});
                    const b = await r.json();
                    return b.data || [];
                }} catch(e) {{ return []; }}
            }}""")

            if not versions:
                log.warning(f"No versions found for {target.strftime('%Y-%m-%d')}. Nothing to sync.")
                sys.exit(0)

            version_key = versions[0].get("versionKey")
            log.info(f"Version key: {version_key}")

            # ── Get S3 URL ────────────────────────────────────────────────────
            s3_url = None
            for attempt in range(5):
                log.info(f"Fetching S3 URL (attempt {attempt+1}/5)...")
                s3_url = page.evaluate(f"""async () => {{
                    try {{
                        const r = await fetch('/api/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}',
                            {{ headers: {{ 'Accept': 'application/json' }} }});
                        if (r.status === 504) return '504';
                        if (!r.ok) return 'error';
                        const b = await r.json();
                        return b.data || null;
                    }} catch(e) {{ return 'error'; }}
                }}""")

                if s3_url and s3_url not in ("504", "error"):
                    log.info(f"Got S3 URL: {s3_url[:60]}...")
                    break
                log.warning(f"  Attempt {attempt+1} failed ({s3_url}). Waiting 30s...")
                time.sleep(30)

            if not s3_url or s3_url in ("504", "error"):
                log.error("Could not get S3 URL after 5 attempts.")
                sys.exit(1)

        except Exception as e:
            log.error(f"Playwright error: {e}")
            sys.exit(1)
        finally:
            browser.close()

    # ── Download CSV into memory (no file saved!) ─────────────────────────────
    log.info("Downloading CSV directly into memory...")
    resp = requests.get(s3_url, stream=True, timeout=120)
    resp.raise_for_status()
    csv_bytes = io.BytesIO(resp.content)
    df = pd.read_csv(csv_bytes, encoding="utf-8-sig", low_memory=False)
    log.info(f"CSV loaded into memory: {len(df)} rows, {len(df.columns)} columns.")

    # ── Clean ─────────────────────────────────────────────────────────────────
    df_facts, dim_ingredients, dim_outlets, mapping = clean_dataframe(df)
    if df_facts is None:
        log.error("Cleaning failed. Aborting.")
        sys.exit(1)
    log.info(f"After cleaning: {len(df_facts)} non-zero fact rows.")

    # ── Upload to DB ──────────────────────────────────────────────────────────
    upsert_to_db(df_facts, dim_ingredients, dim_outlets, mapping)
    log.info("Done! Data is live in PostgreSQL.")


if __name__ == "__main__":
    run()

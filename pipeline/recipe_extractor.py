"""
pipeline/recipe_extractor.py
─────────────────────────────
Pulls recipe BOM (Bill of Materials) from SupplyNote /api/recipes
and upserts into dim_recipe_master in PostgreSQL.

Each recipe gives us:
  - dish_name (the finished product)
  - ingredient (raw material)
  - qty_per_portion (how much per batch / batchSize)
  - unit (gm, ml, kg, etc.)
  - yield_factor (yieldPercentage / 100)
"""

import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

PG_HOST = "103.172.150.31"
PG_USER = "new_user"
PG_PASS = "StrongPassword123!"
PG_DB   = "demand_planning"
PG_PORT = 5432


def get_session_and_business_id():
    print("Logging into SupplyNote...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0")
        page = context.new_page()
        page.goto("https://www.supplynote.in/signin")
        page.wait_for_load_state("networkidle")
        page.fill('input[placeholder="Enter your username"]', os.getenv("SUPPLYNOTE_USER"))
        page.fill('input[placeholder="Enter your password"]', os.getenv("SUPPLYNOTE_PASSWORD"))
        page.click('button:has-text("LOG IN")')
        page.wait_for_load_state("networkidle")
        raw_id = page.evaluate("localStorage.getItem('business')")
        business_id = raw_id.replace('"', '') if raw_id else "65b205675255c93a41dd7849"
        cookies = context.cookies()
        browser.close()

    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])
    session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    return session, business_id


def pull_recipes(session, business_id):
    print("Fetching recipes from SupplyNote...")
    r = session.get(f"https://www.supplynote.in/api/recipes?buisness={business_id}")
    if r.status_code != 200:
        print(f"Failed to fetch recipes: {r.status_code}")
        return []
    data = r.json()
    recipes = data.get("data", [])
    print(f"Got {len(recipes)} recipes")
    return recipes


def parse_recipes(recipes):
    """Flatten recipe list into rows for dim_recipe_master."""
    rows = []
    for recipe in recipes:
        # Dish name
        names = recipe.get("name", [])
        dish_name = names[0] if names else recipe.get("_id", "Unknown")

        # SKU code
        recipe_ids = recipe.get("recipeId", [])
        sku_code = recipe_ids[0] if recipe_ids else ""

        batch_size = float(recipe.get("batchSize", 1) or 1)
        recipe_unit = recipe.get("rUnit", "piece")

        # Ingredients
        ingredients = recipe.get("ingredients", [])
        for ing in ingredients:
            product = ing.get("product", {})
            ingredient_name = product.get("productTitle", "Unknown")

            quantity = float(ing.get("quantity", 0) or 0)
            # qty is per batch — normalize to per portion (per 1 unit of output)
            qty_per_portion = quantity / batch_size if batch_size > 0 else quantity

            ing_unit_info = ing.get("ingredientUnit", {})
            unit = ing_unit_info.get("unit", product.get("baseUnit", "g"))

            # Yield factor from product
            yield_pct = float(product.get("yieldPercentage", 100) or 100)
            yield_factor = yield_pct / 100.0

            rows.append({
                "dish_name":       dish_name,
                "sku_code":        sku_code,
                "ingredient":      ingredient_name,
                "qty_per_portion": round(qty_per_portion, 6),
                "unit":            unit,
                "yield_factor":    yield_factor,
            })

    print(f"Parsed {len(rows)} ingredient rows from {len(recipes)} recipes")
    return rows


def ensure_table(conn):
    """Create dim_recipe_master table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_recipe_master (
                dish_name       TEXT NOT NULL,
                sku_code        TEXT,
                ingredient      TEXT NOT NULL,
                qty_per_portion FLOAT,
                unit            TEXT,
                yield_factor    FLOAT DEFAULT 1.0,
                PRIMARY KEY (dish_name, ingredient)
            );
        """)
    conn.commit()
    print("Table dim_recipe_master ready.")


def upsert_recipes(conn, rows):
    if not rows:
        print("No rows to upsert.")
        return

    # Deduplicate on (dish_name, ingredient)
    unique = {}
    for row in rows:
        key = (row["dish_name"], row["ingredient"])
        unique[key] = row
    values = [(r["dish_name"], r["sku_code"], r["ingredient"],
               r["qty_per_portion"], r["unit"], r["yield_factor"])
              for r in unique.values()]

    upsert_sql = """
        INSERT INTO dim_recipe_master (dish_name, sku_code, ingredient, qty_per_portion, unit, yield_factor)
        VALUES %s
        ON CONFLICT (dish_name, ingredient) DO UPDATE SET
            sku_code        = EXCLUDED.sku_code,
            qty_per_portion = EXCLUDED.qty_per_portion,
            unit            = EXCLUDED.unit,
            yield_factor    = EXCLUDED.yield_factor;
    """
    with conn.cursor() as cur:
        execute_values(cur, upsert_sql, values)
    conn.commit()
    print(f"Upserted {len(values)} recipe rows into dim_recipe_master!")


def main():
    session, business_id = get_session_and_business_id()
    print(f"Business ID: {business_id}")

    recipes = pull_recipes(session, business_id)
    rows = parse_recipes(recipes)

    conn = psycopg2.connect(
        host=PG_HOST, user=PG_USER, password=PG_PASS, dbname=PG_DB, port=PG_PORT
    )
    ensure_table(conn)
    upsert_recipes(conn, rows)
    conn.close()

    print("Recipe extraction complete!")


if __name__ == "__main__":
    main()

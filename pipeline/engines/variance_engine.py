import os
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def run_variance_engine():
    pg_url = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"
    engine = create_engine(pg_url)

    logger.info("Starting Variance Engine...")

    with engine.connect() as conn:
        # 1. Ensure schema exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS variance_settings (
                ingredient TEXT PRIMARY KEY,
                green_threshold FLOAT NOT NULL,
                yellow_threshold FLOAT NOT NULL
            );
        """))
        
        # Seed global fallback
        conn.execute(text("""
            INSERT INTO variance_settings (ingredient, green_threshold, yellow_threshold)
            VALUES ('*', 5.0, 15.0)
            ON CONFLICT (ingredient) DO NOTHING;
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fact_variance (
                date DATE,
                outlet TEXT,
                ingredient TEXT,
                expected_qty FLOAT,
                actual_qty FLOAT,
                variance_qty FLOAT,
                variance_pct FLOAT,
                unit TEXT,
                PRIMARY KEY (date, outlet, ingredient)
            );
        """))
        conn.commit()

        # 2. Define rolling window (Last 7 days up to yesterday)
        # Why up to yesterday? Because today's SupplyNote data isn't fully logged yet.
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=6)
        
        logger.info(f"Computing variance for window: {start_date} to {end_date}")

        # 3. Calculate Expected and Actual Usage directly in SQL to prevent Pandas MemoryErrors
        # Delete the rolling window dates to replace them cleanly
        conn.execute(text(f"DELETE FROM fact_variance WHERE date >= '{start_date}' AND date <= '{end_date}'"))
        
        logger.info("Computing variance and upserting directly inside PostgreSQL...")
        
        upsert_sql = f"""
            WITH expected AS (
                SELECT 
                    CAST(o.created_at_ist AS DATE) as date,
                    lower(trim(o.store_name)) as outlet,
                    lower(trim(rm.ingredient)) as ingredient,
                    MAX(rm.unit) as unit,
                    SUM(CAST(i.quantity AS NUMERIC) * CAST(am.multiplier AS NUMERIC) * CAST(rm.qty_per_unit AS NUMERIC) + CAST(am.additive_offset AS NUMERIC)) as expected_qty
                FROM pos_order_items i
                JOIN pos_orders o ON i.order_id = o.id
                JOIN item_alias_mapping am ON am.pos_name = i.item_name
                    AND (am.pos_option = i.option_names OR am.pos_option IS NULL)
                JOIN recipe_master rm ON rm.dish_name = am.recipe_name
                WHERE CAST(o.created_at_ist AS DATE) >= '{start_date}'
                  AND CAST(o.created_at_ist AS DATE) <= '{end_date}'
                GROUP BY CAST(o.created_at_ist AS DATE), lower(trim(o.store_name)), lower(trim(rm.ingredient))
            ),
            actual AS (
                SELECT 
                    date,
                    lower(trim(outlet)) as outlet,
                    lower(trim(sku)) as ingredient,
                    SUM(qty_sold) as actual_qty
                FROM fact_daily_sales
                WHERE date >= '{start_date}' AND date <= '{end_date}'
                GROUP BY date, lower(trim(outlet)), lower(trim(sku))
            )
            INSERT INTO fact_variance (date, outlet, ingredient, expected_qty, actual_qty, variance_qty, variance_pct, unit)
            SELECT 
                COALESCE(e.date, a.date) as date,
                initcap(COALESCE(e.outlet, a.outlet)) as outlet,
                initcap(COALESCE(e.ingredient, a.ingredient)) as ingredient,
                COALESCE(e.expected_qty, 0) as expected_qty,
                COALESCE(a.actual_qty, 0) as actual_qty,
                COALESCE(a.actual_qty, 0) - COALESCE(e.expected_qty, 0) as variance_qty,
                CASE 
                    WHEN COALESCE(e.expected_qty, 0) > 0 THEN 
                        ((COALESCE(a.actual_qty, 0) - COALESCE(e.expected_qty, 0)) / COALESCE(e.expected_qty, 0)) * 100.0
                    ELSE 100.0
                END as variance_pct,
                COALESCE(e.unit, 'units') as unit
            FROM expected e
            FULL OUTER JOIN actual a 
                ON e.date = a.date 
                AND e.outlet = a.outlet 
                AND e.ingredient = a.ingredient
            WHERE COALESCE(e.expected_qty, 0) > 0 OR COALESCE(a.actual_qty, 0) > 0
        """
        conn.execute(text(upsert_sql))
        conn.commit()
            
    logger.info("Variance Engine completed successfully.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(r'd:\demand-planning\.env')
    run_variance_engine()

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

        # 3. Calculate Expected Usage (Recipe Explosion)
        # We join POS items -> Alias -> Recipe Master
        expected_sql = f"""
            SELECT 
                CAST(o.created_at_ist AS DATE) as date,
                o.store_name as outlet,
                rm.ingredient,
                rm.unit,
                SUM(CAST(i.quantity AS NUMERIC) * CAST(am.multiplier AS NUMERIC) * CAST(rm.qty_per_unit AS NUMERIC) + CAST(am.additive_offset AS NUMERIC)) as expected_qty
            FROM pos_order_items i
            JOIN pos_orders o ON i.order_id = o.id
            -- We match on exact POS name or via Alias
            JOIN item_alias_mapping am ON am.pos_name = i.item_name
                -- If option matters, we match it. Otherwise fallback to NULL option
                AND (am.pos_option = i.option_names OR am.pos_option IS NULL)
            JOIN recipe_master rm ON rm.dish_name = am.recipe_name
            WHERE CAST(o.created_at_ist AS DATE) >= '{start_date}'
              AND CAST(o.created_at_ist AS DATE) <= '{end_date}'
            GROUP BY CAST(o.created_at_ist AS DATE), o.store_name, rm.ingredient, rm.unit
        """
        expected_df = pd.read_sql(expected_sql, conn)
        
        # 4. Calculate Actual Usage (SupplyNote)
        actual_sql = f"""
            SELECT 
                date,
                outlet,
                sku as ingredient,
                SUM(qty_sold) as actual_qty
            FROM fact_daily_sales
            WHERE date >= '{start_date}' AND date <= '{end_date}'
            GROUP BY date, outlet, sku
        """
        actual_df = pd.read_sql(actual_sql, conn)
        

    if expected_df.empty:
        logger.warning("No expected usage found in the rolling window.")
        return

    # 5. Merge and Diff
    logger.info("Diffing expected vs actual...")
    # Convert dates to datetime to ensure clean merges
    expected_df['date'] = pd.to_datetime(expected_df['date'])
    actual_df['date'] = pd.to_datetime(actual_df['date'])
    
    # standardize strings
    expected_df['outlet'] = expected_df['outlet'].str.strip().str.lower()
    actual_df['outlet'] = actual_df['outlet'].str.strip().str.lower()
    expected_df['ingredient'] = expected_df['ingredient'].str.strip().str.lower()
    actual_df['ingredient'] = actual_df['ingredient'].str.strip().str.lower()

    merged = pd.merge(expected_df, actual_df, on=['date', 'outlet', 'ingredient'], how='outer').fillna({'expected_qty': 0, 'actual_qty': 0})
    
    # We only care if expected OR actual > 0
    merged = merged[(merged['expected_qty'] > 0) | (merged['actual_qty'] > 0)].copy()

    # Variance = Actual - Expected. Positive means we used MORE than we should have (wastage/theft)
    merged['variance_qty'] = merged['actual_qty'] - merged['expected_qty']
    
    # % Variance (careful with div by zero)
    merged['variance_pct'] = 0.0
    mask = merged['expected_qty'] > 0
    merged.loc[mask, 'variance_pct'] = (merged.loc[mask, 'variance_qty'] / merged.loc[mask, 'expected_qty']) * 100
    # If expected is 0 but we actually used it, that's infinite variance (or an unmapped recipe). We cap at 100% for display.
    merged.loc[~mask, 'variance_pct'] = 100.0

    # Ensure date is string for SQL
    merged['date'] = merged['date'].dt.strftime('%Y-%m-%d')
    
    # Title-case for display
    merged['outlet'] = merged['outlet'].str.title()
    merged['ingredient'] = merged['ingredient'].str.title()
    
    # Default unit if missing
    merged['unit'] = merged['unit'].fillna('units')
    
    # Point 4: Distinct count sanity check before insert
    distinct_ingredients = merged['ingredient'].nunique()

    # 6. Upsert into fact_variance
    logger.info(f"Upserting {len(merged)} variance records into fact_variance... (Distinct Ingredients: {distinct_ingredients})")
    
    with engine.begin() as conn:
        # Delete the rolling window dates to replace them cleanly
        conn.execute(text(f"DELETE FROM fact_variance WHERE date >= '{start_date}' AND date <= '{end_date}'"))
        
        if not merged.empty:
            merged.to_sql('fact_variance', conn, if_exists='append', index=False)
            
    logger.info("Variance Engine completed successfully.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(r'd:\demand-planning\.env')
    run_variance_engine()

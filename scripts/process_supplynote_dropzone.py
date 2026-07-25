"""
Database processing script for zero-demand reconstruction
"""
import os
import glob
import logging
import pandas as pd
from dotenv import load_dotenv

load_dotenv(r'd:\demand-planning\.env')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s")
log = logging.getLogger("process_dropzone")

def run():
    # DROPZONE_DIR env var is set by the GitHub Actions workflow.
    # Falls back to a sibling folder for local development.
    dropzone_dir = os.getenv(
        'DROPZONE_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'supplynote_dropzone')
    )
    csv_files = glob.glob(os.path.join(dropzone_dir, "*.csv"))
    
    # 1. Verify File Count and Size
    expected_count = 195
    if len(csv_files) != expected_count:
        log.warning(f"Expected {expected_count} files, but found {len(csv_files)}! Continuing anyway, but please verify.")
    else:
        log.info(f"Verified exactly {expected_count} files are present.")
        
    for f in csv_files:
        size_mb = os.path.getsize(f) / (1024 * 1024)
        if size_mb < 50:
            log.warning(f"File {os.path.basename(f)} seems suspiciously small ({size_mb:.1f} MB). Might be truncated.")

    log.info(f"Extracting mapping and facts from {len(csv_files)} files...")

    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import psycopg2
        
        # Schema setup (quick connection)
        conn = psycopg2.connect(
            host=os.getenv("PG_HOST", "***REDACTED-DB-HOST***"),
            user=os.getenv("PG_USER", "new_user"),
            password=os.getenv("PG_PASS", "***REDACTED-DB-PASSWORD***"),
            dbname=os.getenv("PG_DB", "demand_planning"),
            port=os.getenv("PG_PORT", "5432"),
            connect_timeout=10
        )
        conn.autocommit = False
        cursor = conn.cursor()

        # Update Tables with new schema
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
                sku VARCHAR,
                PRIMARY KEY (outlet, sku)
            );
            CREATE TABLE IF NOT EXISTS fact_daily_sales (
                date DATE,
                sku VARCHAR,
                outlet VARCHAR,
                qty_sold NUMERIC,
                currently_available NUMERIC,
                oos VARCHAR,
                PRIMARY KEY (date, sku, outlet)
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()

        from psycopg2.extras import execute_values
        
        for file in csv_files:
            try:
                log.info(f"Processing {os.path.basename(file)}...")
                df = pd.read_csv(file, encoding='utf-8-sig', low_memory=False)
                
                # Map columns
                date_col = next((c for c in df.columns if 'date' in c.lower()), None)
                qty_col = 'plannedDemand' if 'plannedDemand' in df.columns else next((c for c in df.columns if 'qty' in c.lower() or 'demand' in c.lower()), None)
                
                sku_col = 'ingredientCode' if 'ingredientCode' in df.columns else 'IngredientCode'
                sku_name_col = 'ingredientName' if 'ingredientName' in df.columns else 'IngredientName'
                cat_col = 'ingredientCategory' if 'ingredientCategory' in df.columns else None
                pack_col = 'isPackaged' if 'isPackaged' in df.columns else None
                unit_col = 'measuringUnit' if 'measuringUnit' in df.columns else None
                
                outlet_col = 'kitchenCode' if 'kitchenCode' in df.columns else 'KitchenCode'
                outlet_name_col = 'kitchenName' if 'kitchenName' in df.columns else 'KitchenName'
                city_col = 'city' if 'city' in df.columns else None
                
                oos_col = 'oos' if 'oos' in df.columns else None
                avail_col = 'currentlyAvailable' if 'currentlyAvailable' in df.columns else None

                if not all([date_col, qty_col, sku_col, outlet_col]):
                    log.error(f"Missing critical columns in {file}")
                    continue

                # Force types
                df[sku_col] = df[sku_col].astype(str).str.strip()
                df[outlet_col] = df[outlet_col].astype(str).str.strip()
                df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0.0)
                
                if avail_col:
                    df[avail_col] = pd.to_numeric(df[avail_col], errors='coerce').fillna(0.0)

                dim_ingredients = {}
                dim_outlets = {}
                
                # Build Dimensions
                ing_cols = [c for c in [sku_col, sku_name_col, cat_col, pack_col, unit_col] if c]
                if ing_cols:
                    unique_ing = df[ing_cols].drop_duplicates(subset=[sku_col])
                    if sku_col in unique_ing.columns:
                        dim_ingredients = unique_ing.set_index(sku_col).to_dict('index')
                
                out_cols = [c for c in [outlet_col, outlet_name_col, city_col] if c]
                if out_cols:
                    unique_out = df[out_cols].drop_duplicates(subset=[outlet_col])
                    if outlet_col in unique_out.columns:
                        dim_outlets = unique_out.set_index(outlet_col).to_dict('index')
                        
                unique_combos = df[[outlet_col, sku_col]].drop_duplicates()
                map_data = list(unique_combos.itertuples(index=False, name=None))
                
                # Facts
                df_facts = df.copy()
                if len(df_facts) > 0:
                    rename_map = {
                        date_col: 'date', 
                        sku_name_col: 'sku',
                        sku_col: 'sku_code', 
                        outlet_name_col: 'outlet',
                        outlet_col: 'outlet_code',
                        qty_col: 'qty_sold'
                    }
                    if avail_col: rename_map[avail_col] = 'currently_available'
                    if oos_col: rename_map[oos_col] = 'oos'
                    
                    df_facts = df_facts.rename(columns=rename_map)
                    df_facts['date'] = pd.to_datetime(df_facts['date'], format='%d-%m-%Y', errors='coerce')
                    
                    keep_cols = ['date', 'sku', 'sku_code', 'outlet', 'outlet_code', 'qty_sold']
                    if avail_col: keep_cols.append('currently_available')
                    if oos_col: keep_cols.append('oos')
                    
                    df_facts = df_facts[keep_cols]
                    
                    # Grouping as safety net
                    agg_funcs = {'qty_sold': 'sum', 'sku': 'first', 'outlet': 'first'}
                    if 'currently_available' in df_facts.columns: agg_funcs['currently_available'] = 'first'
                    if 'oos' in df_facts.columns: agg_funcs['oos'] = 'first'
                    
                    df_facts = df_facts.groupby(["date", "sku_code", "outlet_code"], as_index=False).agg(agg_funcs)
                    
                    df_fact_export = df_facts.copy()
                    df_fact_export = df_fact_export.dropna(subset=['date'])
                    df_fact_export['date'] = df_fact_export['date'].dt.strftime("%Y-%m-%d")
                    if 'currently_available' not in df_fact_export.columns:
                        df_fact_export['currently_available'] = 0.0
                    if 'oos' not in df_fact_export.columns:
                        df_fact_export['oos'] = None
                        
                    # CRITICAL: Reorder columns to match the Postgres COPY statement exactly!
                    # The COPY statement expects: (date, sku, sku_code, outlet, outlet_code, qty_sold, currently_available, oos)
                    export_cols = ['date', 'sku', 'sku_code', 'outlet', 'outlet_code', 'qty_sold', 'currently_available', 'oos']
                    df_fact_export = df_fact_export[export_cols]

                # Open DB connection exactly when needed to prevent idle timeout
                conn = psycopg2.connect(
                    host=os.getenv("PG_HOST", "***REDACTED-DB-HOST***"),
                    user=os.getenv("PG_USER", "new_user"),
                    password=os.getenv("PG_PASS", "***REDACTED-DB-PASSWORD***"),
                    dbname=os.getenv("PG_DB", "demand_planning"),
                    port=os.getenv("PG_PORT", "5432"),
                    connect_timeout=30,
                    keepalives=1,
                    keepalives_idle=15,
                    keepalives_interval=5,
                    keepalives_count=5
                )
                conn.autocommit = False
                cursor = conn.cursor()

                # Database Upserts for this file
                ing_data = [(sku, d.get(sku_name_col, ''), d.get(cat_col, ''), str(d.get(pack_col, '')), d.get(unit_col, '')) for sku, d in dim_ingredients.items()]
                if ing_data:
                    execute_values(cursor, """
                        INSERT INTO dim_ingredients (sku, name, category, is_packaged, measuring_unit) 
                        VALUES %s
                        ON CONFLICT (sku) DO UPDATE SET 
                            name = EXCLUDED.name, category = EXCLUDED.category, 
                            is_packaged = EXCLUDED.is_packaged, measuring_unit = EXCLUDED.measuring_unit
                    """, ing_data, page_size=10000)
                    
                out_data = [(outlet, d.get(outlet_name_col, ''), d.get(city_col, '')) for outlet, d in dim_outlets.items()]
                if out_data:
                    execute_values(cursor, """
                        INSERT INTO dim_outlets (outlet, name, city) VALUES %s
                        ON CONFLICT (outlet) DO UPDATE SET 
                            name = EXCLUDED.name, city = EXCLUDED.city
                    """, out_data, page_size=10000)
                    
                if map_data:
                    execute_values(cursor, """
                        INSERT INTO kitchen_ingredient_mapping (outlet, sku) VALUES %s
                        ON CONFLICT (outlet, sku) DO NOTHING
                    """, map_data, page_size=10000)
                    
                if not df_fact_export.empty:
                    
                    # Ensure numerical columns are formatted as integers so PostgreSQL COPY doesn't complain about ".0" decimals
                    df_fact_export['qty_sold'] = df_fact_export['qty_sold'].astype(float).round().astype(int)
                    df_fact_export['currently_available'] = df_fact_export['currently_available'].astype(float).round().astype(int)
                    
                    import io
                    chunk_size = 50000
                    total_chunks = (len(df_fact_export) - 1) // chunk_size + 1
                    
                    for i in range(0, len(df_fact_export), chunk_size):
                        chunk = df_fact_export.iloc[i:i+chunk_size]
                        csv_buffer = io.StringIO()
                        chunk.to_csv(csv_buffer, index=False, header=True)
                        csv_buffer.seek(0)
                        
                        # Create temporary table for this chunk
                        cursor.execute("""
                            CREATE TEMP TABLE tmp_fact_daily_sales (LIKE fact_daily_sales INCLUDING DEFAULTS);
                        """)
                        
                        # Native PostgreSQL bulk COPY
                        cursor.copy_expert("COPY tmp_fact_daily_sales(date, sku, sku_code, outlet, outlet_code, qty_sold, currently_available, oos) FROM STDIN WITH CSV HEADER", csv_buffer)
                        
                        # Fast UPSERT from temp table to main table
                        cursor.execute("""
                            INSERT INTO fact_daily_sales (date, sku, sku_code, outlet, outlet_code, qty_sold, currently_available, oos)
                            SELECT date, sku, sku_code, outlet, outlet_code, qty_sold, currently_available, oos FROM tmp_fact_daily_sales
                            ON CONFLICT (date, sku_code, outlet_code) DO UPDATE SET 
                                sku = EXCLUDED.sku,
                                outlet = EXCLUDED.outlet,
                                qty_sold = EXCLUDED.qty_sold,
                                currently_available = EXCLUDED.currently_available,
                                oos = EXCLUDED.oos;
                        """)
                        
                        cursor.execute("DROP TABLE tmp_fact_daily_sales;")
                        conn.commit()
                        if total_chunks > 1:
                            log.info(f"Committed chunk {i//chunk_size + 1}/{total_chunks} for {os.path.basename(file)}")
                log.info(f"Successfully upserted data for {os.path.basename(file)}")
                
                # Delete file after successful commit
                os.remove(file)
                log.info(f"Deleted {os.path.basename(file)}")
                
            except Exception as e:
                if 'conn' in locals() and conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                log.error(f"Failed to process {file}: {e}")
            finally:
                if 'cursor' in locals() and cursor:
                    cursor.close()
                if 'conn' in locals() and conn:
                    conn.close()

        log.info("Finished scanning all files.")
        
    except Exception as e:
        log.error(f"Database operation failed: {e}")
        


if __name__ == "__main__":
    run()

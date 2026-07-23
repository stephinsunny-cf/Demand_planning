"""
Database processing script for zero-demand reconstruction
"""
import os
import glob
import logging
import pandas as pd

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
        from backend.database import get_db_connection
        
        conn = get_db_connection()
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
                kitchen_ingredient_mapping = set()
                
                # Build Dimensions
                ing_cols = [c for c in [sku_col, sku_name_col, cat_col, pack_col, unit_col] if c]
                if ing_cols:
                    unique_ing = df[ing_cols].drop_duplicates()
                    for _, row in unique_ing.iterrows():
                        sku = row[sku_col]
                        dim_ingredients[sku] = {
                            'name': row.get(sku_name_col, ''),
                            'category': row.get(cat_col, ''),
                            'isPackaged': row.get(pack_col, ''),
                            'unit': row.get(unit_col, '')
                        }
                
                out_cols = [c for c in [outlet_col, outlet_name_col, city_col] if c]
                if out_cols:
                    unique_out = df[out_cols].drop_duplicates()
                    for _, row in unique_out.iterrows():
                        outlet = row[outlet_col]
                        dim_outlets[outlet] = {
                            'name': row.get(outlet_name_col, ''),
                            'city': row.get(city_col, '')
                        }
                        
                unique_combos = df[[outlet_col, sku_col]].drop_duplicates()
                for _, row in unique_combos.iterrows():
                    kitchen_ingredient_mapping.add((row[outlet_col], row[sku_col]))
                
                # Facts
                df_facts = df.copy()
                fact_data = []
                if len(df_facts) > 0:
                    rename_map = {date_col: 'date', sku_col: 'sku', outlet_col: 'outlet', qty_col: 'qty_sold'}
                    if avail_col: rename_map[avail_col] = 'currently_available'
                    if oos_col: rename_map[oos_col] = 'oos'
                    
                    df_facts = df_facts.rename(columns=rename_map)
                    df_facts['date'] = pd.to_datetime(df_facts['date'], errors='coerce')
                    
                    keep_cols = ['date', 'sku', 'outlet', 'qty_sold']
                    if avail_col: keep_cols.append('currently_available')
                    if oos_col: keep_cols.append('oos')
                    
                    df_facts = df_facts[keep_cols]
                    
                    # Grouping as safety net
                    agg_funcs = {'qty_sold': 'sum'}
                    if 'currently_available' in df_facts.columns: agg_funcs['currently_available'] = 'first'
                    if 'oos' in df_facts.columns: agg_funcs['oos'] = 'first'
                    
                    df_facts = df_facts.groupby(["date", "sku", "outlet"], as_index=False).agg(agg_funcs)
                    
                    for _, row in df_facts.iterrows():
                        if pd.isna(row["date"]): continue
                        date_str = row["date"].strftime("%Y-%m-%d")
                        avail = row.get("currently_available", 0.0)
                        oos = row.get("oos", None)
                        if pd.isna(oos): oos = None
                        fact_data.append((date_str, row["sku"], row["outlet"], row["qty_sold"], avail, oos))

                # Database Upserts for this file
                ing_data = [(sku, d['name'], d['category'], str(d['isPackaged']), d['unit']) for sku, d in dim_ingredients.items()]
                if ing_data:
                    execute_values(cursor, """
                        INSERT INTO dim_ingredients (sku, name, category, is_packaged, measuring_unit) 
                        VALUES %s
                        ON CONFLICT (sku) DO UPDATE SET 
                            name = EXCLUDED.name, category = EXCLUDED.category, 
                            is_packaged = EXCLUDED.is_packaged, measuring_unit = EXCLUDED.measuring_unit
                    """, ing_data)
                    
                out_data = [(outlet, d['name'], d['city']) for outlet, d in dim_outlets.items()]
                if out_data:
                    execute_values(cursor, """
                        INSERT INTO dim_outlets (outlet, name, city) VALUES %s
                        ON CONFLICT (outlet) DO UPDATE SET 
                            name = EXCLUDED.name, city = EXCLUDED.city
                    """, out_data)
                    
                map_data = list(kitchen_ingredient_mapping)
                if map_data:
                    execute_values(cursor, """
                        INSERT INTO kitchen_ingredient_mapping (outlet, sku) VALUES %s
                        ON CONFLICT (outlet, sku) DO NOTHING
                    """, map_data)
                    
                if fact_data:
                    # Convert fact_data to a DataFrame for easy CSV serialization
                    df_fact_export = pd.DataFrame(fact_data, columns=['date', 'sku', 'outlet', 'qty_sold', 'currently_available', 'oos'])
                    
                    # Ensure numerical columns are formatted as integers so PostgreSQL COPY doesn't complain about ".0" decimals
                    df_fact_export['qty_sold'] = df_fact_export['qty_sold'].astype(float).round().astype(int)
                    df_fact_export['currently_available'] = df_fact_export['currently_available'].astype(float).round().astype(int)
                    
                    import io
                    csv_buffer = io.StringIO()
                    df_fact_export.to_csv(csv_buffer, index=False, header=True)
                    csv_buffer.seek(0)
                    
                    # Create temporary table identical to fact_daily_sales
                    cursor.execute("""
                        CREATE TEMP TABLE tmp_fact_daily_sales (LIKE fact_daily_sales INCLUDING DEFAULTS) ON COMMIT DROP;
                    """)
                    
                    # Native PostgreSQL bulk COPY
                    cursor.copy_expert("COPY tmp_fact_daily_sales(date, sku, outlet, qty_sold, currently_available, oos) FROM STDIN WITH CSV HEADER", csv_buffer)
                    
                    # Fast UPSERT from temp table to main table
                    cursor.execute("""
                        INSERT INTO fact_daily_sales (date, sku, outlet, qty_sold, currently_available, oos)
                        SELECT date, sku, outlet, qty_sold, currently_available, oos FROM tmp_fact_daily_sales
                        ON CONFLICT (date, sku, outlet) DO UPDATE SET 
                            qty_sold = EXCLUDED.qty_sold,
                            currently_available = EXCLUDED.currently_available,
                            oos = EXCLUDED.oos;
                    """)
                    
                conn.commit()
                log.info(f"Successfully upserted data for {os.path.basename(file)}")
                
                # Delete file after successful commit
                os.remove(file)
                log.info(f"Deleted {os.path.basename(file)}")
                
            except Exception as e:
                conn.rollback()
                log.error(f"Failed to process {file}: {e}")

        cursor.close()
        try:
            from backend.database import _pool
            if _pool: _pool.putconn(conn)
        except: pass

        log.info("Finished scanning all files.")
        
    except Exception as e:
        log.error(f"Database operation failed: {e}")
        


if __name__ == "__main__":
    run()

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

    all_facts = []
    
    # Using dictionaries to keep track of dimension attributes
    dim_ingredients = {}
    dim_outlets = {}
    kitchen_ingredient_mapping = set()

    for file in csv_files:
        try:
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

            # Build Dimensions cumulatively
            # Ingredients
            ing_cols = [c for c in [sku_col, sku_name_col, cat_col, pack_col, unit_col] if c]
            if ing_cols:
                unique_ing = df[ing_cols].drop_duplicates()
                for _, row in unique_ing.iterrows():
                    sku = row[sku_col]
                    if sku not in dim_ingredients:
                        dim_ingredients[sku] = {
                            'name': row.get(sku_name_col, ''),
                            'category': row.get(cat_col, ''),
                            'isPackaged': row.get(pack_col, ''),
                            'unit': row.get(unit_col, '')
                        }
            
            # Outlets
            out_cols = [c for c in [outlet_col, outlet_name_col, city_col] if c]
            if out_cols:
                unique_out = df[out_cols].drop_duplicates()
                for _, row in unique_out.iterrows():
                    outlet = row[outlet_col]
                    if outlet not in dim_outlets:
                        dim_outlets[outlet] = {
                            'name': row.get(outlet_name_col, ''),
                            'city': row.get(city_col, '')
                        }
                    
            # Mapping (Valid combos)
            unique_combos = df[[outlet_col, sku_col]].drop_duplicates()
            for _, row in unique_combos.iterrows():
                kitchen_ingredient_mapping.add((row[outlet_col], row[sku_col]))

            # Filter non-zero demand (!= 0 allows negatives to pass through)
            df_facts = df[df[qty_col] != 0].copy()
            
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
                all_facts.append(df_facts)
                
            log.info(f"Processed {os.path.basename(file)}")

        except Exception as e:
            log.error(f"Failed to process {file}: {e}")

    log.info("Finished scanning all files. Preparing database upserts...")

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
        
        from psycopg2.extras import execute_values
        
        log.info("Upserting dim_ingredients...")
        ing_data = [(sku, d['name'], d['category'], str(d['isPackaged']), d['unit']) for sku, d in dim_ingredients.items()]
        if ing_data:
            execute_values(cursor, """
                INSERT INTO dim_ingredients (sku, name, category, is_packaged, measuring_unit) 
                VALUES %s
                ON CONFLICT (sku) DO UPDATE SET 
                    name = EXCLUDED.name, category = EXCLUDED.category, 
                    is_packaged = EXCLUDED.is_packaged, measuring_unit = EXCLUDED.measuring_unit
            """, ing_data)
            
        log.info("Upserting dim_outlets...")
        out_data = [(outlet, d['name'], d['city']) for outlet, d in dim_outlets.items()]
        if out_data:
            execute_values(cursor, """
                INSERT INTO dim_outlets (outlet, name, city) VALUES %s
                ON CONFLICT (outlet) DO UPDATE SET 
                    name = EXCLUDED.name, city = EXCLUDED.city
            """, out_data)
            
        log.info("Upserting kitchen_ingredient_mapping...")
        map_data = list(kitchen_ingredient_mapping)
        if map_data:
            execute_values(cursor, """
                INSERT INTO kitchen_ingredient_mapping (outlet, sku) VALUES %s
                ON CONFLICT (outlet, sku) DO NOTHING
            """, map_data)
            
        if all_facts:
            master_df = pd.concat(all_facts, ignore_index=True)
            # Grouping by date, sku, outlet as safety net
            agg_funcs = {'qty_sold': 'sum'}
            if 'currently_available' in master_df.columns: agg_funcs['currently_available'] = 'first'
            if 'oos' in master_df.columns: agg_funcs['oos'] = 'first'
            
            master_df = master_df.groupby(["date", "sku", "outlet"], as_index=False).agg(agg_funcs)
            
            log.info(f"Upserting {len(master_df)} facts into fact_daily_sales...")
            fact_data = []
            for _, row in master_df.iterrows():
                if pd.isna(row["date"]): continue
                date_str = row["date"].strftime("%Y-%m-%d")
                avail = row.get("currently_available", 0.0)
                oos = row.get("oos", None)
                if pd.isna(oos): oos = None
                fact_data.append((date_str, row["sku"], row["outlet"], row["qty_sold"], avail, oos))
                
            if fact_data:
                execute_values(cursor, """
                    INSERT INTO fact_daily_sales (date, sku, outlet, qty_sold, currently_available, oos)
                    VALUES %s
                    ON CONFLICT (date, sku, outlet) DO UPDATE SET 
                        qty_sold = EXCLUDED.qty_sold,
                        currently_available = EXCLUDED.currently_available,
                        oos = EXCLUDED.oos
                """, fact_data, page_size=10000)
            log.info(f"Upserted {len(fact_data)} facts successfully.")

        conn.commit()
        cursor.close()
        try:
            from backend.database import _pool
            if _pool: _pool.putconn(conn)
        except: pass

        log.info("Database load complete!")

        # 3. Archive the processed files so they aren't reprocessed tomorrow
        import shutil
        archive_dir = os.path.join(dropzone_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        for f in csv_files:
            try:
                shutil.move(f, os.path.join(archive_dir, os.path.basename(f)))
            except Exception as e:
                log.warning(f"Could not move {f} to archive: {e}")
        log.info(f"Archived {len(csv_files)} files.")

    except Exception as e:
        log.error(f"Database operation failed: {e}")

if __name__ == "__main__":
    run()

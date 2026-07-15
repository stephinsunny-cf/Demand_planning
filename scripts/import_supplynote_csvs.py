"""
Manual SupplyNote CSV Importer
Reads any CSV files dropped in the `supplynote_dropzone` folder,
deduplicates them, and inserts them into the fact_daily_sales database.
"""
import os
import glob
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s")
log = logging.getLogger("csv_importer")

def run():
    dropzone_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'supplynote_dropzone')
    csv_files = glob.glob(os.path.join(dropzone_dir, "*.csv"))
    
    if not csv_files:
        log.warning(f"No CSV files found in {dropzone_dir}! Please download 'All Ingredient Data' from SupplyNote and place them there.")
        return
        
    all_data = []
    
    for file in csv_files:
        try:
            # SupplyNote CSVs often have BOM headers or weird encodings
            df = pd.read_csv(file, encoding='utf-8-sig')
            
            # Find the relevant columns via keyword matching
            cols = [c.lower() for c in df.columns]
            
            # Date
            date_col = next((c for c in df.columns if 'date' in c.lower()), None)
            # Ingredient Name
            sku_col = next((c for c in df.columns if 'name' in c.lower() or 'ingredient' in c.lower() or 'item' in c.lower()), None)
            # Outlet
            outlet_col = next((c for c in df.columns if 'kitchen' in c.lower() or 'outlet' in c.lower() or 'store' in c.lower()), None)
            # Quantity
            qty_col = next((c for c in df.columns if 'qty' in c.lower() or 'quantity' in c.lower() or 'demand' in c.lower()), None)
            
            if not date_col or not sku_col or not qty_col:
                log.error(f"Could not identify required columns in {file}. Found columns: {list(df.columns)}")
                continue
                
            # Rename columns to standard schema
            mapping = {date_col: 'date', sku_col: 'sku', qty_col: 'qty_sold'}
            if outlet_col:
                mapping[outlet_col] = 'outlet'
            else:
                df['outlet'] = 'Koramangala' # default fallback
                mapping['outlet'] = 'outlet'
                
            df = df.rename(columns=mapping)
            
            # Ensure proper types
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['qty_sold'] = pd.to_numeric(df['qty_sold'], errors='coerce')
            
            # Drop invalid rows
            df = df.dropna(subset=['date', 'sku', 'qty_sold'])
            
            all_data.append(df[['date', 'sku', 'outlet', 'qty_sold']])
            log.info(f"Successfully processed {file} ({len(df)} rows)")
            
        except Exception as e:
            log.error(f"Failed to process {file}: {e}")
            
    if not all_data:
        log.warning("No valid data was extracted from the CSVs.")
        return
        
    # Combine and Deduplicate
    master_df = pd.concat(all_data, ignore_index=True)
    master_df = master_df.groupby(["date", "sku", "outlet"], as_index=False)["qty_sold"].sum()
    
    log.info(f"Total aggregated unique records to insert: {len(master_df)}")
    
    # Push to Database
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        log.info("Uploading to database (Upserting to prevent duplicates)...")
        inserted = 0
        for _, row in master_df.iterrows():
            try:
                # Convert date back to string for postgres
                date_str = row["date"].strftime("%Y-%m-%d")
                cursor.execute("""
                    INSERT INTO fact_daily_sales (date, sku, outlet, qty_sold)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date, sku, outlet) DO UPDATE SET qty_sold = EXCLUDED.qty_sold
                """, (date_str, row["sku"], row["outlet"], row["qty_sold"]))
                inserted += 1
            except Exception as e:
                log.warning(f"DB Insert failed for {row['sku']}: {e}")
                
        conn.commit()
        cursor.close()
        conn.close()
        log.info(f"Successfully upserted {inserted} records in the PostgreSQL database!")
        
        # Move processed files to archive so they don't get processed again
        archive_dir = os.path.join(dropzone_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        import shutil
        for file in csv_files:
            shutil.move(file, os.path.join(archive_dir, os.path.basename(file)))
        log.info(f"Moved {len(csv_files)} processed files to {archive_dir}")
        
    except Exception as e:
        log.error(f"Failed to connect or insert into database: {e}")

if __name__ == "__main__":
    run()

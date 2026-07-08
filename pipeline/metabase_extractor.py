import os
import requests
import json
import pandas as pd
import clickhouse_connect
from dotenv import load_dotenv
import io

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")

def fetch_table_chunk(query_str):
    payload = {
        "database": 2, # urbanpiper
        "type": "native",
        "native": {
            "query": query_str
        }
    }
    
    print(f"  -> Executing: {query_str}")
    
    form_data = {
        "query": json.dumps(payload)
    }
    csv_headers = {"x-api-key": METABASE_API_KEY}
    
    res = requests.post(f"{METABASE_URL}/api/dataset/csv", headers=csv_headers, data=form_data)
    
    if res.status_code != 200:
        print(f"  -> Error fetching data: {res.status_code}")
        return None
        
    try:
        df = pd.read_csv(io.StringIO(res.text), on_bad_lines='skip')
        print(f"  -> Fetched {len(df)} rows")
        return df
    except Exception as e:
        print(f"  -> Error parsing CSV: {e}")
        return None

def copy_to_local_clickhouse():
    print("Connecting to local ClickHouse...")
    dest = clickhouse_connect.get_client(password='admin123', database='default')
    
    print("Wiping existing database and tables...")
    dest.command("DROP DATABASE IF EXISTS demand_planning")
    dest.command("CREATE DATABASE demand_planning")

    dest_db = clickhouse_connect.get_client(password='admin123', database='demand_planning')

    # Month chunks to bypass Metabase API limit
    months = [
        ('2025-12-01', '2026-01-01'),
        ('2026-01-01', '2026-02-01'),
        ('2026-02-01', '2026-03-01'),
        ('2026-03-01', '2026-04-01'),
        ('2026-04-01', '2026-05-01'),
        ('2026-05-01', '2026-06-01'),
        ('2026-06-01', '2026-07-01')
    ]

    tables = [
        {
            "name": "orders",
            "date_col": "created_at_ist"
        },
        {
            "name": "order_items",
            "date_col": "order_created_at_ist"
        }
    ]

    for table in tables:
        print(f"\n{'='*50}")
        print(f"Processing target table: {table['name']}")
        print(f"{'='*50}")
        
        table_created = False
        
        for start_dt, end_dt in months:
            print(f"Chunk: {start_dt} to {end_dt}")
            query = f"SELECT * FROM `curefoods_test`.`{table['name']}` WHERE {table['date_col']} >= '{start_dt}' AND {table['date_col']} < '{end_dt}'"
            
            df = fetch_table_chunk(query)
            
            if df is None or len(df) == 0:
                print("  -> No data for chunk, skipping.")
                continue
                
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('-', '_')
            
            # Remove exact duplicates in this chunk
            initial_len = len(df)
            df.drop_duplicates(inplace=True)
            if initial_len - len(df) > 0:
                print(f"  -> Removed {initial_len - len(df)} duplicate rows")

            # Clean nulls and convert everything to string to avoid schema errors across chunks
            df = df.astype(str)
            df.replace({'nan': None, 'None': None, 'NaT': None, '<NA>': None}, inplace=True)
            
            if not table_created:
                # Create table schema with ALL strings
                cols_def = [f"`{col}` Nullable(String)" for col in df.columns]
                create_stmt = f"CREATE TABLE {table['name']} ({', '.join(cols_def)}) ENGINE = MergeTree() ORDER BY tuple()"
                dest_db.command(create_stmt)
                table_created = True
                
            try:
                dest_db.insert_df(table['name'], df, column_names=list(df.columns))
                print(f"  -> Successfully inserted chunk into ClickHouse")
            except Exception as e:
                print(f"  -> ERROR inserting chunk: {e}")

if __name__ == "__main__":
    copy_to_local_clickhouse()

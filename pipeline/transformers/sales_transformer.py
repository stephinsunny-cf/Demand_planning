import clickhouse_connect

def run_sales_transformer():
    client = clickhouse_connect.get_client(password='admin123')
    
    print("Creating fact_orders_raw view...")
    # The dashboard needs a 'created_at' column to count today's orders
    client.command("""
        CREATE OR REPLACE VIEW fact_orders_raw AS 
        SELECT 
            created_at_ist AS created_at,
            *
        FROM orders
    """)
    
    print("Creating fact_daily_sales table...")
    client.command("""
        CREATE TABLE IF NOT EXISTS fact_daily_sales (
            date Date,
            sku String,
            brand String,
            outlet String,
            city String,
            qty_sold Int64,
            revenue Float64,
            order_count Int64
        ) ENGINE = MergeTree()
        ORDER BY (date, sku, outlet)
    """)
    
    print("Truncating old data...")
    client.command("TRUNCATE TABLE IF EXISTS fact_daily_sales")
    
    print("Pulling raw data into Pandas for transformation...")
    import pandas as pd
    
    df_orders = client.query_df("SELECT id, created_at_ist, brand_name, store_name, city FROM orders WHERE created_at_ist IS NOT NULL")
    df_items = client.query_df("SELECT order_id, item_name, quantity, total_price FROM order_items WHERE item_name IS NOT NULL")
    
    print("Joining and cleaning data...")
    df = pd.merge(df_orders, df_items, left_on='id', right_on='order_id', how='inner')
    
    # Parse date strings like 'February 2, 2026, 5:25 PM'
    df['date'] = pd.to_datetime(df['created_at_ist']).dt.date
    
    # Clean up prices and quantities by removing commas (e.g. "1,160" -> "1160")
    df['total_price'] = pd.to_numeric(df['total_price'].astype(str).str.replace(',', ''), errors='coerce').fillna(0.0)
    df['quantity'] = pd.to_numeric(df['quantity'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    print("Aggregating sales...")
    agg = df.groupby(['date', 'item_name', 'brand_name', 'store_name', 'city'], dropna=False).agg(
        qty_sold=('quantity', 'sum'),
        revenue=('total_price', 'sum'),
        order_count=('id', 'nunique')
    ).reset_index()
    
    # Rename columns to match fact_daily_sales schema
    agg = agg.rename(columns={
        'item_name': 'sku',
        'brand_name': 'brand',
        'store_name': 'outlet'
    })
    
    # Ensure no NaN strings
    agg = agg.where(pd.notnull(agg), None)
    
    print("Inserting aggregated data back into ClickHouse...")
    client.insert_df('fact_daily_sales', agg)
    
    # Check count
    count = client.command("SELECT count() FROM fact_daily_sales")
    print(f"Success! Inserted {count} aggregated daily sales records.")

if __name__ == "__main__":
    run_sales_transformer()

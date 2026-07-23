from backend.database import query_df
try:
    df = query_df("SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name IN ('pos_orders', 'pos_order_items', 'fact_daily_sales', 'recipe_master') AND data_type = 'text'")
    print(df.to_string())
except Exception as e:
    print('ERROR:', e)

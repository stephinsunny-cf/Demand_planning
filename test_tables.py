from backend.database import query_df
print(query_df("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))

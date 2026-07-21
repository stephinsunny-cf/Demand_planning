from backend.database import query_df
cache_df = query_df("SELECT endpoint FROM app_cache")
print(cache_df)

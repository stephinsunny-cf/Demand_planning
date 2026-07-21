import sys
import os
sys.path.append(os.path.abspath("d:/demand-planning"))
from backend.database import query_df
df = query_df("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
print(df)
for t in df['table_name']:
    c = query_df(f"SELECT COUNT(*) FROM {t}")
    print(t, c.iloc[0,0])

from backend.database import query_df
import json

df = query_df("SELECT payload FROM app_cache WHERE endpoint = 'dashboard_summary'")
if df.empty:
    print('ROW IS EMPTY OR MISSING!')
else:
    payload = df['payload'].iloc[0]
    if isinstance(payload, str): payload = json.loads(payload)
    print(json.dumps({k: v for k, v in payload.items() if k != 'recent_alerts' and k != 'vendor_performance' and k != 'top_movers'}, indent=2))

import time
import asyncio
import warnings
from backend.database import query_df

warnings.filterwarnings('ignore')

# WARMUP
query_df("SELECT 1")

async def test_concurrent():
    t0 = time.time()
    cache_task = asyncio.to_thread(query_df, "SELECT payload FROM app_cache WHERE endpoint = 'dashboard_summary'")
    alerts_task = asyncio.to_thread(query_df, "SELECT severity, COUNT(*) AS cnt FROM alerts WHERE resolved = 0 GROUP BY severity")
    recent_task = asyncio.to_thread(query_df, "SELECT alert_id, alert_type, severity, message, sku, outlet, ingredient, created_at, resolved FROM alerts ORDER BY created_at DESC LIMIT 10")
    
    await asyncio.gather(cache_task, alerts_task, recent_task)
    
    t1 = time.time()
    print(f"Total concurrent time: {t1-t0:.4f}s")

if __name__ == "__main__":
    asyncio.run(test_concurrent())

# Data Pipeline

The data pipeline runs asynchronously from the web application, typically via scheduled scripts (cron jobs).

## 1. UrbanPiper (Dish Sales) Sync
- **Script:** `scripts/sync_urbanpiper_daily.py`
- **Source:** UrbanPiper data via the internal Curefoods Metabase API (`clickhouse.eatfit.in`).
- **Flow:** 
  1. Authenticates with Metabase using `METABASE_API_KEY`.
  2. Executes a saved Metabase card/query to get yesterday's POS orders.
  3. Transforms and inserts the data into the local `pos_orders` and `pos_order_items` Postgres tables.

## 2. SupplyNote (Kitchen Consumption) Sync
- **Script:** `scripts/fetch_and_load_supplynote.py` (and `fetch_supplynote_history.py`)
- **Source:** SupplyNote web portal.
- **Flow:**
  1. Uses Playwright to spin up a headless Chromium browser.
  2. Logs in using `SUPPLYNOTE_USER` and `SUPPLYNOTE_PASSWORD`.
  3. Navigates to the Kitchen Consumption reports page.
  4. Triggers a CSV export for a specific date range.
  5. Parses the downloaded CSV and inserts it into the `fact_daily_sales` Postgres table.
- **Warning:** Highly fragile. If SupplyNote changes their HTML DOM structure (IDs, classes), the Playwright script will fail.

## 3. Engine Runs
- **Scripts:** `pipeline/main.py`, `pipeline/engines/forecast_engine.py`, `variance_engine.py`
- **Flow:** After raw data is ingested, these engines run to calculate moving averages, predict future demand, and flag discrepancies between predicted ingredient usage and actual SupplyNote usage.

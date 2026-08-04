# Changelog

## Recent Fixes (August 2026)

### Frontend & UI
- **Fixed:** Removed ₹0 financial metric cards (Cost Value, Avg Cost) from the Kitchen Consumption tab because SupplyNote only provides quantity data. Replaced with "Total Qty Consumed".
- **Fixed:** Changed default Kitchen Consumption date window from 30 days to 7 days. This prevents the UI from timing out when querying the 111M row `fact_daily_sales` table.

### Backend (FastAPI)
- **Fixed:** Added `total_qty` to the `/api/sales/summary` endpoint response.
- **Fixed:** Resolved `SUM(text) does not exist` crashes in PostgreSQL by adding `CAST(NULLIF(REPLACE(col, ',', ''), '') AS numeric)` to handle comma-formatted strings in POS orders.
- **Fixed:** Dropped `date` from the `GROUP BY` clause in `/api/sales` for fact_daily_sales to prevent massive 6-million group fan-outs, reducing query time from ~40s to ~4s.
- **Fixed:** Enforced RBAC (Role-Based Access Control) accurately. Unauthenticated requests now properly return `401 Unauthorized` instead of being bypassed.

### Data Pipeline
- **Verified:** SupplyNote extractor hardcodes `revenue` and `order_count` to 0 as expected, correctly mapping `sold` to `qty_sold`.

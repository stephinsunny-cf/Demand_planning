# Known Issues & Tech Debt

## 1. SupplyNote Scraper Fragility (High Risk)
**Issue:** The data pipeline relies on a Playwright script (`fetch_and_load_supplynote.py`) clicking DOM elements on the SupplyNote website.
**Impact:** If SupplyNote changes their UI, adds CAPTCHA, or alters the CSV format, the pipeline will silently fail, and Kitchen Consumption data will go stale.
**Fix:** Lobby SupplyNote for API access, or set up robust alerting when the script fails.

## 2. Vercel Deployment Sync (Medium Risk)
**Issue:** Legacy Vite configurations or failing Next.js builds cause Vercel to serve stale frontends. 
**Impact:** Developers push code, see it pass locally, but users don't see it.
**Fix:** Fix all strict TypeScript errors causing Vercel builds to fail, and ensure the domain points to the correct Next.js Vercel project.

## 3. Render Cold Starts (Medium Risk)
**Issue:** The FastAPI backend spins down after 15 minutes on the free tier.
**Impact:** Users experience a 30-60 second hang ("Authenticating...") on their first login of the day.
**Fix:** Upgrade Render to a paid tier.

## 4. Massive Table Performance (Medium Risk)
**Issue:** `fact_daily_sales` has over 111 million rows.
**Impact:** Unfiltered queries will cause Postgres to churn and the API to timeout (30s+).
**Fix:** We currently enforce a strict 7-day default window and aggregate by `sku, outlet` (dropping `date` grouping) in the UI. A long-term fix involves creating materialized views for historical reporting.

## 5. Missing Financial Data in SupplyNote
**Issue:** SupplyNote only provides quantity (`qty_sold`). The backend hardcodes `revenue` and `order_count` to 0.
**Impact:** The UI cannot display "Ingredient Cost Value".
**Fix:** The backend needs to join `fact_daily_sales` against `ingredient_master` to calculate costs dynamically based on `qty_sold * unit_cost`.

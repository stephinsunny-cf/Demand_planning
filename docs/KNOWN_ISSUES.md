# Known Issues & Tech Debt

## 1. SupplyNote Scraper Fragility (High Risk)
**Issue:** The data pipeline relies on a Playwright script (`fetch_and_load_supplynote.py`) clicking DOM elements on the SupplyNote website.
**Impact:** If SupplyNote changes their UI, adds CAPTCHA, or alters the CSV format, the pipeline will silently fail, and Kitchen Consumption data will go stale.
**Fix:** Lobby SupplyNote for API access, or set up robust alerting when the script fails.

## 2. Vercel Deployment Sync (Medium Risk)
**Issue:** Legacy Vite configurations or failing Next.js builds cause Vercel to serve stale frontends. 
**Impact:** Developers push code, see it pass locally, but users don't see it.
**Fix:** Fix all strict TypeScript errors causing Vercel builds to fail, and ensure the domain points to the correct Next.js Vercel project.

## 3. Render Cold Starts (Mitigated 2026-08-06)
**Issue:** The FastAPI backend spins down after 15 minutes on the free tier.
**Impact:** Users experience a 30-60 second hang ("Authenticating...") on their first login of the day.
**Fix:** Two changes applied 2026-08-06: (1) an external cron-job.org ping to `/health` every 10 minutes keeps the free-tier instance from ever going idle long enough to sleep; (2) `backend/auth.py`'s Supabase token verification (previously a live network call on *every* request) is now cached for up to 1 hour per token, so even a brief Supabase hiccup no longer makes every module feel slow at once. The `is_active`/role check is unaffected and still runs fresh on every request, so admin deactivation still cuts a user off immediately. Upgrading Render to a paid tier remains the more permanent fix if the free-tier cron workaround ever proves insufficient.

## 4. Massive Table Performance (Medium Risk)
**Issue:** `fact_daily_sales` has over 111 million rows.
**Impact:** Unfiltered queries will cause Postgres to churn and the API to timeout (30s+).
**Fix:** We currently enforce a strict 7-day default window and aggregate by `sku, outlet` (dropping `date` grouping) in the UI. A long-term fix involves creating materialized views for historical reporting.

## 5. Missing Financial Data in SupplyNote
**Issue:** SupplyNote only provides quantity (`qty_sold`). The backend hardcodes `revenue` and `order_count` to 0.
**Impact:** The UI cannot display "Ingredient Cost Value".
**Fix:** The backend needs to join `fact_daily_sales` against `dim_ingredients` to calculate costs dynamically based on `qty_sold * unit_cost`.

## 6. Variance "Needs Mapping" — ingredient identity + dish-recipe coverage (Fixed/Ongoing 2026-08-06)
**Issue:** Two separate bugs, both surfacing as inflated "Needs Mapping" counts on the Variance page:
1. **Ingredient identity mismatch (fixed):** `recipe_master.ingredient` stores SKU codes; `fact_daily_sales.sku` and `fact_variance.ingredient` store a mix of codes and display names. `backend/routers/variance.py` and `pipeline/engines/variance_engine.py` compared these as raw strings with no normalization, so a large majority of genuinely-mapped ingredients were misclassified as unmapped. Fixed by normalizing both sides through `dim_sku` and `dim_ingredients` before comparing — see "Ingredient Identity" in `docs/DATABASE_SCHEMA.md`.
2. **Dish-recipe coverage gap (data entry, not a code bug):** `item_alias_mapping` only maps a fraction of dishes actually sold (475 total vs. 220 of 226 dishes unmapped in one sample week). A dish missing here contributes zero expected quantity for every one of its ingredients regardless of fix #1. Someone with recipe knowledge needs to add these dishes to `item_alias_mapping` / `recipe_master`.
**Impact:** Before the fix, the vast majority of variance rows showed a meaningless "Needs Mapping" badge instead of a real RED/YELLOW/GREEN variance status, making the Variance page largely unusable for spotting real discrepancies.
**Fix:** Fix #1 is live (both the display query and the underlying engine calculation). Fix #2 is ongoing — `alert_engine.py`'s `NO_RECIPE` rule now flags newly-sold, unmapped dishes automatically (previously this rule compared the wrong pair of columns and never actually caught anything), so this gap gets caught within a day going forward instead of silently growing for months.

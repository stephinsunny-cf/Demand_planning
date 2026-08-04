# Operations Runbook

## 1. Login takes forever or spins indefinitely
**Cause:** The Render backend is on a free tier and goes to sleep.
**Fix:** Wait 60 seconds. If it errors out, click Login again. The second attempt will be instant. To fix permanently, upgrade Render to a paid tier ($7/mo).

## 2. Kitchen Consumption (SupplyNote) data is missing
**Cause:** The Playwright scraper likely failed due to a DOM change on the SupplyNote website, or the password changed.
**Fix:** 
1. Check the logs for `scripts/fetch_and_load_supplynote.py`.
2. Ensure `SUPPLYNOTE_PASSWORD` in `.env` is correct.
3. If DOM changed, update the Playwright selectors in the script.

## 3. Frontend changes aren't showing up live
**Cause:** The Vercel build is failing silently, so Vercel is serving an old build.
**Fix:** 
1. Go to Vercel Dashboard.
2. Open the failing deployment.
3. Check the build logs. Usually it's a TypeScript error or missing Environment Variable in Vercel settings.
4. Fix the code, push to `main`.

## 4. Backend changes aren't showing up live
**Cause:** Render is set to manual deploy.
**Fix:** Go to Render Dashboard -> Manual Deploy -> Deploy latest commit.

## 5. 500 Errors on Sales Dashboards
**Cause:** Data casting issues (commas in text fields acting as numbers) or query timeouts due to large date ranges on `fact_daily_sales` (111M+ rows).
**Fix:** Ensure queries use `REPLACE(col, ',', '')` before casting, and ensure date ranges are restricted (e.g., 7 days max for default views) and indexed.

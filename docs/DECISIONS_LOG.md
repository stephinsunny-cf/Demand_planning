# Decisions Log

## 1. Database: PostgreSQL over ClickHouse
**Decision:** Shifted primary operational database from ClickHouse to PostgreSQL.
**Why:** ClickHouse is excellent for append-only OLAP, but the app required frequent updates, row-level locks, and complex relational joins for user profiles, recipes, and variance outputs. Postgres handles the web-backend workload much better.

## 2. API: Metabase API over direct ClickHouse queries
**Decision:** Extract UrbanPiper data via Metabase API endpoints instead of direct DB queries.
**Why:** Direct queries to the production ClickHouse risked impacting live operational systems. Metabase provides a safe abstraction layer with pre-optimized cards.

## 3. Data Extraction: Playwright for SupplyNote
**Decision:** Use a headless browser (Playwright) to scrape SupplyNote.
**Why:** SupplyNote does not offer a developer-facing REST API for historical kitchen consumption. Scraping CSVs via the UI was the only automated pathway.

## 4. Backend Deployment: Auto-deploy on `main` only
**Decision:** Render auto-deploy is enabled, scoped specifically to the `main` branch. (Previously disabled entirely, for the same reason below — revisited once the `development` → verify → merge-to-`main` workflow was established as the actual working pattern.)
**Why:** Code only reaches `main` after being pushed to `development` first and verified there, so by the time it lands on `main` it's already been checked — auto-deploying from `main` doesn't skip that verification step. If auto-deploy were scoped to `development` too, unverified in-progress code would go live immediately, which is exactly what the original decision was trying to prevent.
**Testing `development` before merging:** No separate staging service — changes are run and verified locally (`uvicorn backend.main:app --reload`, or pipeline scripts directly) against the real database before merging to `main`. Considered a second Render service auto-deploying from `development` for a live preview environment, but decided against it for now: extra infrastructure to maintain, and it would need its own database (or risk unverified code writing bad data to the shared production DB) to be safe. Revisit if local-only testing stops being sufficient.

## 5. Aggregation Strategy: Application-level vs DB-level
**Decision:** Heavy aggregations (grouping by SKU/Outlet) are done in PostgreSQL (`GROUP BY`), passing only small aggregated result sets (thousands of rows) to Pandas/FastAPI.
**Why:** Transferring 10M+ rows over the network to process in Pandas caused massive memory bloat and API timeouts. Pushing computation to Postgres keeps the API fast.

## 6. Forecasting Engine: LightGBM over Prophet
**Decision:** Replaced the per-combo Prophet forecast engine (`pipeline/engines/forecast_engine.py`) with a single global LightGBM model (`pipeline/engines/lightgbm_engine.py`) as the active engine in `pipeline/main.py`.
**Why:** Prophet fits one model per SKU x outlet combo (~18-20K separate fits), which made a full run take anywhere from tens of minutes to multiple hours and was hitting GitHub Actions' timeout. LightGBM trains one shared model across all combos and completes in ~7-19 minutes.
**Validation:** Tested rigorously before switching — a full-scale, no-sampling, rolling-origin backtest across Feb-April 2026 (including real festivals) showed LightGBM winning 78.64% vs Prophet's 72.25% (see `pipeline/run_lightgbm_backtest_v2.py` / `run_prophet_backtest_v2.py`). A live-data check on a single recent week then showed LightGBM scoring far worse (57%) with accuracy collapsing the further ahead it predicted — traced to a real bug: multi-day predictions were computed in one shot off a feature panel that filled not-yet-known future dates with 0, so rolling/lag features for later days in the horizon were increasingly built from fake zeros instead of real sales. Fixed by predicting recursively (one day at a time, feeding each day's own prediction back in as that day's known value for the next day's features) — accuracy on the same week then matched the backtest almost exactly (78.44%, stable across the whole week), and confirmed LightGBM winning both the large historical backtest and live current data before merging.
**Rollback:** `forecast_engine.py` (Prophet) is left in the codebase, just no longer imported by `pipeline/main.py`. Re-wiring it back in is a one-line change if LightGBM ever needs to be rolled back; `prophet`/`pystan` were removed from `requirements.txt` since nothing in the active pipeline needs them anymore — reinstall locally if reviving it.

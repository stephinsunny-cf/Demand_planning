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

## 4. Backend Deployment: Manual on Render
**Decision:** Render auto-deploy is disabled.
**Why:** To prevent unverified code or broken pipeline scripts from immediately pushing to production and breaking the active forecasting engine.

## 5. Aggregation Strategy: Application-level vs DB-level
**Decision:** Heavy aggregations (grouping by SKU/Outlet) are done in PostgreSQL (`GROUP BY`), passing only small aggregated result sets (thousands of rows) to Pandas/FastAPI.
**Why:** Transferring 10M+ rows over the network to process in Pandas caused massive memory bloat and API timeouts. Pushing computation to Postgres keeps the API fast.

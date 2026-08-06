# Database Schema

The primary database is PostgreSQL. Below are the key tables.

## Core Operational Tables
- **`user_profiles`**: Maps Supabase UUIDs (`user_id`) to application roles (`admin`, `planning_manager`, etc.) and manages active status.
- **`pos_orders`**: Header-level data for UrbanPiper sales (Order ID, total amount, brand, store, timestamp).
- **`pos_order_items`**: Line-item data for UrbanPiper sales (Item name, quantity, price). Joins to `pos_orders` via `order_id`.
- **`fact_daily_sales`**: Massive table (111M+ rows) storing SupplyNote daily kitchen consumption. Contains `date`, `sku` (ingredient), `outlet`, `qty_sold`. Note: `revenue` and `order_count` are hardcoded to 0.

## Master Data (Reference)
- **`recipe_master`**: Maps a dish (`dish_name`) to its raw/semi-finished ingredient components (`ingredient`) and expected quantities per unit (`qty_per_unit`). Used by the variance engine. **`ingredient` here is a SKU code** (e.g. `"CFIDG177"`), not a display name — see "Ingredient Identity" below.
- **`dim_sku`**: Code↔name catalog (`sku_code`, `sku_name`) for tracked procurement items.
- **`dim_ingredients`**: A second, broader code↔name catalog (`sku`, `name`, `category`), populated from SupplyNote — covers semi-finished/prepped items `dim_sku` doesn't (parottas, marinated proteins, sauces, etc.).
- **`item_alias_mapping`**: Bridges a sold POS dish name (`pos_name`, from `pos_order_items.item_name`) to its canonical recipe (`recipe_name`, matches `recipe_master.dish_name`), plus a `multiplier`/`additive_offset` for portion scaling.

## Ingredient Identity: Codes vs. Names (read this before touching variance/mapping logic)
Ingredients are identified **inconsistently by design** across tables, and this has caused real bugs (see `docs/KNOWN_ISSUES.md`):
- `recipe_master.ingredient` — almost always a **code** (2,613 of 2,614 distinct values, confirmed 2026-08-06).
- `fact_daily_sales.sku` — almost always a **display name**.
- `fact_variance.ingredient` — a **mix of both**, depending on which side of a join populated that row.

Any code comparing ingredient identity across these tables must first normalize both sides to the same form — translate a code to its name (or vice versa) via `dim_sku` **and** `dim_ingredients` (checking both; an item might only be in one). Comparing raw strings directly, as the original variance code did, silently misclassifies the majority of rows as "unmapped" even when a valid mapping exists.

Separately: `item_alias_mapping` only covers a **fraction of actually-sold dishes** (475 total mapped vs. e.g. 226 distinct dishes sold in a single week, of which 220 had no mapping — checked 2026-08-06). A dish missing from this table contributes **zero** expected quantity for all of its ingredients in the variance engine, regardless of whether the ingredient-identity issue above is fixed. This is a data-entry gap, not a code bug — `alert_engine.py`'s `NO_RECIPE` rule now flags any dish sold in the last 7 days with no `item_alias_mapping` entry, so new gaps surface as alerts instead of accumulating silently.

## Analytical Output
- **`fact_forecast`**: Stores the generated demand forecasts by the forecast engine (`forecast_date`, `sku`, `outlet`, `qty_predicted`).
- **`fact_variance`**: Stores calculated discrepancies (actual consumption vs recipe-expected consumption) per `date`, `outlet`, `ingredient`.

## Notes on Scale
`fact_daily_sales` is heavily populated. Queries against this table **must** use narrow date windows (e.g., 7 days) and group by `sku` and `outlet` instead of doing per-date aggregations for long date ranges to prevent API timeouts.

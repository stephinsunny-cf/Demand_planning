# Database Schema

The primary database is PostgreSQL. Below are the key tables.

## Core Operational Tables
- **`user_profiles`**: Maps Supabase UUIDs (`user_id`) to application roles (`admin`, `planning_manager`, etc.) and manages active status.
- **`pos_orders`**: Header-level data for UrbanPiper sales (Order ID, total amount, brand, store, timestamp).
- **`pos_order_items`**: Line-item data for UrbanPiper sales (Item name, quantity, price). Joins to `pos_orders` via `order_id`.
- **`fact_daily_sales`**: Massive table (111M+ rows) storing SupplyNote daily kitchen consumption. Contains `date`, `sku` (ingredient), `outlet`, `qty_sold`. Note: `revenue` and `order_count` are hardcoded to 0.

## Master Data (Reference)
- **`recipe_master`**: Maps finished goods (Dish Sales) to their raw ingredients and expected quantities. Used by the variance engine.
- **`ingredient_master`**: Details about raw ingredients, shelf life, pack size, and unit cost.

## Analytical Output
- **`forecast_output`**: Stores the generated demand forecasts by the forecast engine.
- **`variance_output`**: Stores calculated discrepancies (actual consumption vs recipe-expected consumption).

## Notes on Scale
`fact_daily_sales` is heavily populated. Queries against this table **must** use narrow date windows (e.g., 7 days) and group by `sku` and `outlet` instead of doing per-date aggregations for long date ranges to prevent API timeouts.

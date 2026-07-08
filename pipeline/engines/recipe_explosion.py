"""
pipeline/engines/recipe_explosion.py — ENGINE 4
─────────────────────────────────────────────────
Converts dish-level demand into ingredient-level demand using recipe master.

Formula: Ingredient Demand = Σ (Forecast Units × Recipe Qty per Portion / Yield Factor)
"""

import logging
from datetime import datetime, timezone, timedelta, date

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import query_df, get_db_connection

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

def run() -> pd.DataFrame:
    """
    Run recipe explosion engine.
    Reads from fact_forecast (next 30 days) and dim_recipe_master.
    Writes to fact_ingredient_demand.
    """
    started_at = datetime.now(IST)
    print("=" * 60)
    print("ENGINE 4: Recipe Explosion - start")

    try:
        # Get recipe master
        recipe_df = query_df(
            "SELECT dish_name, ingredient, qty_per_portion, unit, yield_factor "
            "FROM dim_recipe_master"
        )

        if recipe_df.empty:
            print("Recipe master is empty - cannot explode to ingredients")
            return pd.DataFrame()

        # Get full forecast demand (from fact_forecast)
        today = date.today()
        demand_df = query_df(
            f"SELECT sku, outlet, forecast_date, sum(qty_predicted) AS forecast_units "
            f"FROM fact_forecast "
            f"WHERE forecast_date >= '{today}' "
            f"GROUP BY sku, outlet, forecast_date"
        )

        if demand_df.empty:
            print("No demand data for recipe explosion")
            return pd.DataFrame()

        # Normalise SKU names for join
        demand_df["sku"] = demand_df["sku"].astype(str).str.strip().str.lower()
        recipe_df["dish_name"] = recipe_df["dish_name"].astype(str).str.strip().str.lower()

        # Join demand with recipe
        exploded = demand_df.merge(
            recipe_df,
            left_on="sku",
            right_on="dish_name",
            how="left",
        )

        # Drop rows with no recipe mapping
        exploded = exploded.dropna(subset=["ingredient"])

        if exploded.empty:
            print("No SKUs matched recipe master - check dish name consistency")
            return pd.DataFrame()

        # Ensure numeric types
        exploded["forecast_units"]  = pd.to_numeric(exploded["forecast_units"],  errors="coerce").fillna(0)
        exploded["qty_per_portion"] = pd.to_numeric(exploded["qty_per_portion"], errors="coerce").fillna(0)
        exploded["yield_factor"]    = pd.to_numeric(exploded["yield_factor"],    errors="coerce").fillna(1.0)
        exploded["yield_factor"]    = exploded["yield_factor"].clip(lower=0.01)

        # THE CRITICAL FORMULA: divide by yield factor
        exploded["ingredient_demand"] = (
            exploded["forecast_units"] * exploded["qty_per_portion"] / exploded["yield_factor"]
        )

        # Aggregate total ingredient demand across all SKUs per outlet per date
        ingredient_totals = (
            exploded.groupby(["forecast_date", "outlet", "ingredient", "unit"], as_index=False)
            .agg(total_qty_needed=("ingredient_demand", "sum"))
        )
        ingredient_totals["total_qty_needed"] = ingredient_totals["total_qty_needed"].round(2)

        print(f"Recipe explosion: {len(ingredient_totals)} unique ingredient demand records generated.")

        print("Writing to fact_ingredient_demand...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fact_ingredient_demand (
                        forecast_date DATE,
                        outlet VARCHAR(255),
                        ingredient VARCHAR(255),
                        unit VARCHAR(50),
                        total_qty_needed FLOAT
                    )
                """)
                cur.execute("TRUNCATE TABLE fact_ingredient_demand")
                
                insert_query = """
                    INSERT INTO fact_ingredient_demand (forecast_date, outlet, ingredient, unit, total_qty_needed)
                    VALUES %s
                """
                values = [
                    (row['forecast_date'], row['outlet'], row['ingredient'], row['unit'], float(row['total_qty_needed']))
                    for _, row in ingredient_totals.iterrows()
                ]
                execute_values(cur, insert_query, values)
                conn.commit()
                print(f"Successfully inserted {len(values)} rows to fact_ingredient_demand!")

        return ingredient_totals

    except Exception as exc:
        print(f"Recipe explosion engine failed: {exc}")
        return pd.DataFrame()

if __name__ == "__main__":
    run()

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def main():
    load_dotenv(r'd:\demand-planning\.env')
    pg_url = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"
    engine = create_engine(pg_url)

    print("Fetching untracked POS dishes and evaluating their ingredient impact...")

    # Query:
    # 1. Get all POS items NOT IN item_alias_mapping
    # 2. Try to match them to a recipe_master dish_name via fuzzy or manual ops (for now we assume we know their recipe composition to rank them, wait, if they are unmapped we DON'T know their recipe composition!
    # Ah! If they are unmapped, we don't know their recipe. How can we weight by ingredient cost?
    # The user said: "Since you're now ranking by 'dishes containing at least one of 138 ingredients,' you might still end up prioritizing a dish where only a minor, cheap ingredient (say, a garnish) is in scope... weight the ranking by how much of the dish's total ingredient cost/quantity is covered by tracked SKUs"
    # Wait, if they are UNMAPPED, we can't look up their recipe yet. 
    # But wait, we can look up ALL recipes in recipe_master, filter to those containing the 138 ingredients, and then rank THOSE recipes by how much of their weight is in scope, then tell Ops "Hey, these are the recipes you should look for in the POS data".
    
    query = """
    WITH TrackedIngredients AS (
        SELECT lower(trim(code)) as code FROM procurement_tracker
    ),
    RecipeWeights AS (
        SELECT 
            r.dish_name,
            SUM(r.qty_per_unit) as total_qty,
            SUM(CASE WHEN lower(trim(r.ingredient)) IN (SELECT code FROM TrackedIngredients) THEN r.qty_per_unit ELSE 0 END) as tracked_qty
        FROM recipe_master r
        GROUP BY r.dish_name
    ),
    DishRanking AS (
        SELECT 
            dish_name,
            tracked_qty,
            total_qty,
            CASE WHEN total_qty > 0 THEN (tracked_qty / total_qty) * 100 ELSE 0 END as tracked_pct
        FROM RecipeWeights
        WHERE tracked_qty > 0
    )
    SELECT * FROM DishRanking
    ORDER BY tracked_pct DESC, tracked_qty DESC
    LIMIT 100;
    """
    
    df = pd.read_sql(query, engine)
    df.to_csv(r'C:\Users\HP\.gemini\antigravity-ide\brain\edaba01f-a46a-4e42-8385-c296ad3de1b0\alias_prioritization_scoped.csv', index=False)
    print(f"Exported {len(df)} high-priority recipes to map.")

if __name__ == "__main__":
    main()

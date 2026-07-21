"""backend/routers/recipes.py — GET /api/recipes, PUT /api/recipes/{dish_name}"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from backend.auth     import require_role, UserContext
from backend.database import query_df, get_db

router = APIRouter()


class RecipeUpdateItem(BaseModel):
    ingredient:      str
    qty_per_portion: float
    unit:            str


@router.get("/recipes")
async def get_recipes(
    dish_name: Optional[str] = Query(default=None),
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "culinary_team")),
):
    where = ["1=1"]
    if dish_name: where.append(f"lower(dish_name) LIKE lower('%{dish_name}%')")

    df = query_df(f"""
        SELECT 
            r.dish_name, 
            r.ingredient, 
            r.qty_per_unit AS qty_per_portion, 
            r.unit, 
            1.0 AS yield_factor,
            pt.code as sku_code,
            CASE WHEN pt.ingredient IS NOT NULL THEN true ELSE false END as is_tracked
        FROM recipe_master r
        LEFT JOIN procurement_tracker pt ON r.ingredient = pt.code
        WHERE {' AND '.join(where)}
        ORDER BY r.dish_name, r.ingredient
        LIMIT 2000
    """)
    import pandas as pd
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records") if not df.empty else []


@router.put("/recipes/{dish_name}")
async def update_recipe(
    dish_name: str,
    items: list[RecipeUpdateItem],
    user: UserContext = Depends(require_role("super_admin", "culinary_team")),
):
    """Update recipe ingredients for a dish."""
    import psycopg2
    from psycopg2.extras import execute_values
    from backend.database import get_db_connection

    records = []
    for item in items:
        records.append((
            dish_name.lower().strip(),
            item.ingredient.lower().strip(),
            item.qty_per_portion,
            item.unit
        ))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Delete old recipe for this dish
            cur.execute("DELETE FROM recipe_master WHERE lower(dish_name) = lower(%s)", (dish_name,))
            # Insert new recipe
            insert_query = """
                INSERT INTO recipe_master (dish_name, ingredient, qty_per_unit, unit)
                VALUES %s
            """
            execute_values(cur, insert_query, records)
            conn.commit()

    return {"success": True, "dish_name": dish_name, "items_updated": len(records)}

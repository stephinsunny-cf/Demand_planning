from typing import Optional
from fastapi import APIRouter, Depends
from backend.auth import get_current_user, UserContext, require_role
from backend.database import query_df
from datetime import date, timedelta
import pandas as pd

router = APIRouter()

@router.get("/variance")
async def get_variance(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    outlet:     Optional[str] = None,
    ingredient: Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    # Fetch variance settings
    settings_df = query_df("SELECT * FROM variance_settings")
    settings = {}
    fallback = {'green_threshold': 5.0, 'yellow_threshold': 15.0}
    
    for _, row in settings_df.iterrows():
        if row['ingredient'] == '*':
            fallback = {'green_threshold': float(row['green_threshold']), 'yellow_threshold': float(row['yellow_threshold'])}
        else:
            settings[row['ingredient'].lower()] = {'green_threshold': float(row['green_threshold']), 'yellow_threshold': float(row['yellow_threshold'])}

    # Fetch fact_variance
    where = []
    if start_date and end_date:
        where.append(f"date >= '{start_date}' AND date <= '{end_date}'")
    if outlet:
        where.append(f"lower(outlet) = lower('{outlet}')")
    if ingredient:
        where.append(f"lower(ingredient) LIKE lower('%{ingredient}%')")

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    
    sql = f"""
        SELECT date, outlet, ingredient, unit, 
               sum(expected_qty) as expected_qty, 
               sum(actual_qty) as actual_qty, 
               sum(variance_qty) as variance_qty
        FROM fact_variance
        {where_clause}
        GROUP BY date, outlet, ingredient, unit
        ORDER BY variance_qty DESC
        LIMIT 5000
    """
    df = query_df(sql)
    
    if df.empty:
        return []
        
    records = df.to_dict(orient="records")
    
    # Calculate % variance and flag per record
    for r in records:
        exp = float(r['expected_qty'] or 0)
        act = float(r['actual_qty'] or 0)
        var_qty = float(r['variance_qty'] or 0)
        
        if exp > 0:
            var_pct = (var_qty / exp) * 100
        else:
            var_pct = 100.0 if act > 0 else 0.0
            
        r['variance_pct'] = round(var_pct, 2)
        r['expected_qty'] = round(exp, 2)
        r['actual_qty'] = round(act, 2)
        r['variance_qty'] = round(var_qty, 2)
        
        # Determine flag
        ing_name = r['ingredient'].lower()
        thresh = settings.get(ing_name, fallback)
        
        if exp == 0 and act > 0:
            r['flag'] = 'unmapped'
            r['variance_pct'] = None
        else:
            abs_var = abs(var_pct)
            if abs_var <= thresh['green_threshold']:
                r['flag'] = 'green'
            elif abs_var <= thresh['yellow_threshold']:
                r['flag'] = 'yellow'
            else:
                r['flag'] = 'red'

    return records

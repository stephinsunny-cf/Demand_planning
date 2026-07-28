"""backend/routers/sales.py — GET /api/sales and /api/sales/summary"""

import asyncio
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
import pandas as pd

from backend.database import query_df
from backend.auth import get_current_user, UserContext, require_role
from backend.utils import safe_json_response

router = APIRouter()

def get_end_date_plus_1(end_date_str: str) -> str:
    try:
        return str(date.fromisoformat(end_date_str) + timedelta(days=1))
    except ValueError:
        return str(date.today() + timedelta(days=1))

@router.get("/sales/pos")
def get_sales_pos(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    brand:      Optional[str] = None,
    outlet:     Optional[str] = None,
    city:       Optional[str] = None,
    sku:        Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT MAX(created_at_ist) as max_date FROM pos_orders")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = pd.to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    end_date_plus_1 = get_end_date_plus_1(end_date)
    where = ["o.created_at_ist >= %s", "o.created_at_ist < %s"]
    params = [start_date, end_date_plus_1]

    if brand:  
        where.append("lower(o.brand_name) = lower(%s)")
        params.append(brand)
    if outlet: 
        where.append("lower(o.store_name) = lower(%s)")
        params.append(outlet)
    if city:   
        where.append("lower(o.city) = lower(%s)")
        params.append(city)
    if sku:    
        where.append("lower(i.item_name) LIKE lower(%s)")
        params.append(f"%{sku}%")

    sql = f"""
        SELECT CAST(o.created_at_ist AS DATE) as date, i.item_name as sku, o.brand_name as brand, o.store_name as outlet, o.city,
               sum(i.quantity) AS qty_sold,
               sum(i.total_price) AS revenue,
               count(DISTINCT o.id) AS order_count
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE {' AND '.join(where)}
        GROUP BY CAST(o.created_at_ist AS DATE), i.item_name, o.brand_name, o.store_name, o.city
        ORDER BY date DESC
        LIMIT 5000
    """
    
    df = query_df(sql, tuple(params))
    df = df.where(pd.notnull(df), None)
    return safe_json_response(df.to_dict(orient="records") if not df.empty else [])


@router.get("/sales/pos/summary")
async def get_sales_pos_summary(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT MAX(created_at_ist) as max_date FROM pos_orders")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = pd.to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    end_date_plus_1 = get_end_date_plus_1(end_date)
    sql_params = (start_date, end_date_plus_1)

    task_totals = asyncio.to_thread(query_df, """
        SELECT sum(total_amount) AS total_revenue, count(id) AS total_orders
        FROM pos_orders
        WHERE created_at_ist >= %s AND created_at_ist < %s
    """, sql_params)

    task_unique = asyncio.to_thread(query_df, """
        SELECT count(DISTINCT i.item_name) AS unique_skus
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE o.created_at_ist >= %s AND o.created_at_ist < %s
    """, sql_params)

    task_top = asyncio.to_thread(query_df, """
        SELECT i.item_name as sku, sum(i.quantity) AS total_qty, sum(i.total_price) AS total_revenue
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE o.created_at_ist >= %s AND o.created_at_ist < %s
        GROUP BY i.item_name ORDER BY total_qty DESC LIMIT 10
    """, sql_params)

    task_brand = asyncio.to_thread(query_df, """
        SELECT brand_name as brand, sum(total_amount) AS revenue, count(id) AS orders
        FROM pos_orders
        WHERE created_at_ist >= %s AND created_at_ist < %s
        GROUP BY brand_name ORDER BY revenue DESC
    """, sql_params)

    totals, unique_skus_df, top_skus, by_brand = await asyncio.gather(
        task_totals, task_unique, task_top, task_brand
    )

    total_rev = float(totals["total_revenue"].iloc[0]) if not totals.empty and pd.notna(totals["total_revenue"].iloc[0]) else 0
    total_ord = int(totals["total_orders"].iloc[0]) if not totals.empty and pd.notna(totals["total_orders"].iloc[0]) else 0
    unique_skus = int(unique_skus_df["unique_skus"].iloc[0]) if not unique_skus_df.empty and pd.notna(unique_skus_df["unique_skus"].iloc[0]) else 0

    return safe_json_response({
        "total_revenue":    round(total_rev, 2),
        "total_orders":     total_ord,
        "avg_order_value":  round(total_rev / total_ord, 2) if total_ord > 0 else 0,
        "unique_skus":      unique_skus,
        "top_skus":         top_skus.to_dict(orient="records") if not top_skus.empty else [],
        "sales_by_brand":   by_brand.to_dict(orient="records") if not by_brand.empty else [],
    })


@router.get("/sales")
def get_sales(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    brand:      Optional[str] = None,
    outlet:     Optional[str] = None,
    city:       Optional[str] = None,
    sku:        Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT max(date) as max_date FROM fact_daily_sales")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = pd.to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    where = ["date >= %s", "date <= %s"]
    params = [start_date, end_date]

    if brand:  
        where.append("lower(brand) = lower(%s)")
        params.append(brand)
    if outlet: 
        where.append("lower(outlet) = lower(%s)")
        params.append(outlet)
    if city:   
        where.append("lower(city) = lower(%s)")
        params.append(city)
    if sku:    
        where.append("lower(sku) LIKE lower(%s)")
        params.append(f"%{sku}%")

    sql = f"""
        SELECT date, sku, brand, outlet, city,
               sum(qty_sold) AS qty_sold,
               sum(revenue) AS revenue,
               sum(order_count) AS order_count
        FROM fact_daily_sales
        WHERE {' AND '.join(where)}
        GROUP BY date, sku, brand, outlet, city
        ORDER BY date DESC
        LIMIT 5000
    """
    df = query_df(sql, tuple(params))
    df = df.where(pd.notnull(df), None)
    return safe_json_response(df.to_dict(orient="records") if not df.empty else [])


@router.get("/sales/summary")
async def get_sales_summary(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT max(date) as max_date FROM fact_daily_sales")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = pd.to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    sql_params = (start_date, end_date)

    task_totals = asyncio.to_thread(query_df, """
        SELECT sum(revenue) AS total_revenue,
               sum(order_count) AS total_orders,
               count(DISTINCT sku) AS unique_skus
        FROM fact_daily_sales
        WHERE date >= %s AND date <= %s
    """, sql_params)

    task_top = asyncio.to_thread(query_df, """
        SELECT sku, sum(qty_sold) AS total_qty, sum(revenue) AS total_revenue
        FROM fact_daily_sales
        WHERE date >= %s AND date <= %s
        GROUP BY sku ORDER BY total_qty DESC LIMIT 10
    """, sql_params)

    task_brand = asyncio.to_thread(query_df, """
        SELECT brand, sum(revenue) AS revenue, sum(order_count) AS orders
        FROM fact_daily_sales
        WHERE date >= %s AND date <= %s
        GROUP BY brand ORDER BY revenue DESC
    """, sql_params)

    totals, top_skus, by_brand = await asyncio.gather(task_totals, task_top, task_brand)

    total_rev = float(totals["total_revenue"].iloc[0]) if not totals.empty and pd.notna(totals["total_revenue"].iloc[0]) else 0
    total_ord = int(totals["total_orders"].iloc[0]) if not totals.empty and pd.notna(totals["total_orders"].iloc[0]) else 0
    unique_skus = int(totals["unique_skus"].iloc[0]) if not totals.empty and pd.notna(totals["unique_skus"].iloc[0]) else 0

    return safe_json_response({
        "total_revenue":    round(total_rev, 2),
        "total_orders":     total_ord,
        "avg_order_value":  round(total_rev / total_ord, 2) if total_ord > 0 else 0,
        "unique_skus":      unique_skus,
        "top_skus":         top_skus.to_dict(orient="records") if not top_skus.empty else [],
        "sales_by_brand":   by_brand.to_dict(orient="records") if not by_brand.empty else [],
    })

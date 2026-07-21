"""backend/routers/sales.py — GET /api/sales and /api/sales/summary"""

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import get_current_user, UserContext, require_role
from backend.database import query_df

router = APIRouter()


@router.get("/sales/pos")
async def get_sales_pos(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    brand:      Optional[str] = None,
    outlet:     Optional[str] = None,
    city:       Optional[str] = None,
    sku:        Optional[str] = None, # maps to item_name in POS
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT MAX(CAST(created_at_ist AS DATE)) as max_date FROM pos_orders")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    where = [f"CAST(o.created_at_ist AS DATE) >= '{start_date}'", f"CAST(o.created_at_ist AS DATE) <= '{end_date}'"]
    if brand:  where.append(f"lower(o.brand_name) = lower('{brand}')")
    if outlet: where.append(f"lower(o.store_name) = lower('{outlet}')")
    if city:   where.append(f"lower(o.city) = lower('{city}')")
    if sku:    where.append(f"lower(i.item_name) LIKE lower('%{sku}%')")

    sql = f"""
        SELECT CAST(o.created_at_ist AS DATE) as date, i.item_name as sku, o.brand_name as brand, o.store_name as outlet, o.city,
               sum(CAST(REPLACE(CAST(i.quantity AS TEXT), ',', '') AS NUMERIC)) AS qty_sold,
               sum(CAST(REPLACE(CAST(i.total_price AS TEXT), ',', '') AS NUMERIC)) AS revenue,
               count(DISTINCT o.id) AS order_count
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE {' AND '.join(where)}
        GROUP BY CAST(o.created_at_ist AS DATE), i.item_name, o.brand_name, o.store_name, o.city
        ORDER BY date DESC
        LIMIT 5000
    """
    df = query_df(sql)
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/sales/pos/summary")
async def get_sales_pos_summary(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT MAX(CAST(created_at_ist AS DATE)) as max_date FROM pos_orders")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    totals = query_df(f"""
        SELECT sum(CAST(REPLACE(CAST(total_amount AS TEXT), ',', '') AS NUMERIC)) AS total_revenue,
               count(id) AS total_orders
        FROM pos_orders
        WHERE CAST(created_at_ist AS DATE) >= '{start_date}' AND CAST(created_at_ist AS DATE) <= '{end_date}'
    """)

    unique_skus_df = query_df(f"""
        SELECT count(DISTINCT i.item_name) AS unique_skus
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE CAST(o.created_at_ist AS DATE) >= '{start_date}' AND CAST(o.created_at_ist AS DATE) <= '{end_date}'
    """)

    top_skus = query_df(f"""
        SELECT i.item_name as sku, sum(CAST(REPLACE(CAST(i.quantity AS TEXT), ',', '') AS NUMERIC)) AS total_qty, sum(CAST(REPLACE(CAST(i.total_price AS TEXT), ',', '') AS NUMERIC)) AS total_revenue
        FROM pos_order_items i
        JOIN pos_orders o ON i.order_id = o.id
        WHERE CAST(o.created_at_ist AS DATE) >= '{start_date}' AND CAST(o.created_at_ist AS DATE) <= '{end_date}'
        GROUP BY i.item_name ORDER BY total_qty DESC LIMIT 10
    """)

    by_brand = query_df(f"""
        SELECT brand_name as brand, sum(CAST(REPLACE(CAST(total_amount AS TEXT), ',', '') AS NUMERIC)) AS revenue, count(id) AS orders
        FROM pos_orders
        WHERE CAST(created_at_ist AS DATE) >= '{start_date}' AND CAST(created_at_ist AS DATE) <= '{end_date}'
        GROUP BY brand_name ORDER BY revenue DESC
    """)

    total_rev = float(totals["total_revenue"].iloc[0]) if not totals.empty and not pd.isna(totals["total_revenue"].iloc[0]) else 0
    total_ord = int(totals["total_orders"].iloc[0]) if not totals.empty else 0
    unique_skus = int(unique_skus_df["unique_skus"].iloc[0]) if not unique_skus_df.empty else 0

    return {
        "total_revenue":    round(total_rev, 2),
        "total_orders":     total_ord,
        "avg_order_value":  round(total_rev / total_ord, 2) if total_ord > 0 else 0,
        "unique_skus":      unique_skus,
        "top_skus":         top_skus.to_dict(orient="records") if not top_skus.empty else [],
        "sales_by_brand":   by_brand.to_dict(orient="records") if not by_brand.empty else [],
    }


@router.get("/sales")
async def get_sales(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    brand:      Optional[str] = None,
    outlet:     Optional[str] = None,
    city:       Optional[str] = None,
    sku:        Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        # Get the latest date we have data for, instead of today's date (which might be empty)
        max_date_df = query_df("SELECT max(date) as max_date FROM fact_daily_sales")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    where = [f"date >= '{start_date}'", f"date <= '{end_date}'"]
    if brand:  where.append(f"lower(brand) = lower('{brand}')")
    if outlet: where.append(f"lower(outlet) = lower('{outlet}')")
    if city:   where.append(f"lower(city) = lower('{city}')")
    if sku:    where.append(f"lower(sku) LIKE lower('%{sku}%')")

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
    df = query_df(sql)
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/sales/summary")
async def get_sales_summary(
    start_date: Optional[str] = None,
    end_date:   Optional[str] = None,
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner")),
):
    if not start_date or not end_date:
        max_date_df = query_df("SELECT max(date) as max_date FROM fact_daily_sales")
        if not max_date_df.empty and max_date_df["max_date"].iloc[0] is not None:
            latest = __import__("pandas").to_datetime(max_date_df["max_date"].iloc[0]).date()
            if not end_date: end_date = str(latest)
            if not start_date: start_date = str(latest - timedelta(days=30))
        else:
            if not end_date: end_date = str(date.today())
            if not start_date: start_date = str(date.today() - timedelta(days=30))

    totals = query_df(f"""
        SELECT sum(revenue) AS total_revenue,
               sum(order_count) AS total_orders,
               count(DISTINCT sku) AS unique_skus
        FROM fact_daily_sales
        WHERE date >= '{start_date}' AND date <= '{end_date}'
    """)

    top_skus = query_df(f"""
        SELECT sku, sum(qty_sold) AS total_qty, sum(revenue) AS total_revenue
        FROM fact_daily_sales
        WHERE date >= '{start_date}' AND date <= '{end_date}'
        GROUP BY sku ORDER BY total_qty DESC LIMIT 10
    """)

    by_brand = query_df(f"""
        SELECT brand, sum(revenue) AS revenue, sum(order_count) AS orders
        FROM fact_daily_sales
        WHERE date >= '{start_date}' AND date <= '{end_date}'
        GROUP BY brand ORDER BY revenue DESC
    """)

    total_rev = float(totals["total_revenue"].iloc[0]) if not totals.empty else 0
    total_ord = int(totals["total_orders"].iloc[0]) if not totals.empty else 0
    unique_skus = int(totals["unique_skus"].iloc[0]) if not totals.empty else 0

    return {
        "total_revenue":    round(total_rev, 2),
        "total_orders":     total_ord,
        "avg_order_value":  round(total_rev / total_ord, 2) if total_ord > 0 else 0,
        "unique_skus":      unique_skus,
        "top_skus":         top_skus.to_dict(orient="records") if not top_skus.empty else [],
        "sales_by_brand":   by_brand.to_dict(orient="records") if not by_brand.empty else [],
    }

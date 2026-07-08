"""backend/routers/sales.py — GET /api/sales and /api/sales/summary"""

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.auth     import get_current_user, UserContext, require_role
from backend.database import query_df

router = APIRouter()


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

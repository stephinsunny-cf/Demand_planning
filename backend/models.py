"""
backend/models.py
──────────────────
Pydantic response models for all API endpoints.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Dashboard ─────────────────────────────────────────────────────────────────

class AlertSummary(BaseModel):
    alert_id:   str
    alert_type: str
    severity:   str
    message:    str
    sku:        str
    outlet:     str
    ingredient: str
    created_at: datetime
    resolved:   int

class DashboardSummary(BaseModel):
    total_orders_today:        int
    active_alerts_count:       int
    critical_alerts_count:     int
    skus_at_risk:              int
    forecast_accuracy_percent: float
    last_data_refresh:         Optional[datetime]
    recent_alerts:             List[AlertSummary]


# ── Sales ─────────────────────────────────────────────────────────────────────

class DailySalesRow(BaseModel):
    date:        date
    sku:         str
    brand:       str
    outlet:      str
    city:        str
    qty_sold:    float
    revenue:     float
    order_count: int

class SalesSummary(BaseModel):
    total_revenue:  float
    total_orders:   int
    avg_order_value: float
    unique_skus:    int
    top_skus:       List[dict]
    sales_by_brand: List[dict]


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastRow(BaseModel):
    forecast_date:  date
    sku:            str
    outlet:         str
    qty_predicted:  float
    qty_lower:      float
    qty_upper:      float
    model_run_date: Optional[date]
    actual_qty:     Optional[float] = None  # filled for historical dates

class ForecastResponse(BaseModel):
    sku:            str
    outlet:         str
    historical:     List[ForecastRow]
    forecast:       List[ForecastRow]
    accuracy_score: Optional[float]  # MAPE %


# ── Supply Planning ───────────────────────────────────────────────────────────

class SupplyPlanRow(BaseModel):
    sku:                  str
    kitchen:              str
    forecast_3day:        float
    stock_qty:            float
    safety_stock_qty:     float
    replenishment_needed: float
    status:               str  # RED, YELLOW, GREEN


# ── Recipes ───────────────────────────────────────────────────────────────────

class RecipeRow(BaseModel):
    dish_name:       str
    ingredient:      str
    qty_per_portion: float
    unit:            str
    yield_factor:    float
    updated_at:      Optional[datetime]

class RecipeUpdateRequest(BaseModel):
    ingredient:      str
    qty_per_portion: float
    unit:            str
    yield_factor:    float


# ── Warehouse ─────────────────────────────────────────────────────────────────

class WarehouseRow(BaseModel):
    ingredient:       str
    unit:             str
    total_qty_needed: float
    warehouse_stock:  float
    net_requirement:  float
    status:           str  # RED, YELLOW, GREEN


# ── Procurement ───────────────────────────────────────────────────────────────

class ProcurementRow(BaseModel):
    vendor_name:       str
    ingredient:        str
    net_requirement:   float
    po_qty:            float
    recommended_qty:   float
    moq:               float
    unit:              str
    price:             float
    estimated_cost:    float
    urgency:           str  # URGENT, NORMAL
    expected_delivery: str


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertRow(BaseModel):
    alert_id:   str
    alert_type: str
    severity:   str
    message:    str
    sku:        str
    outlet:     str
    ingredient: str
    created_at: datetime
    resolved:   int
    resolved_at: Optional[datetime]

class AlertResolveResponse(BaseModel):
    success:  bool
    alert_id: str


# ── Reports ───────────────────────────────────────────────────────────────────

class AccuracyPoint(BaseModel):
    week:     str
    accuracy: float

class StockoutPoint(BaseModel):
    week:     str
    incidents: int

class VendorPerformanceRow(BaseModel):
    vendor:         str
    on_time_pct:    float
    total_orders:   int


# ── Admin ─────────────────────────────────────────────────────────────────────

class UserRow(BaseModel):
    id:         str
    email:      str
    role:       str
    created_at: Optional[datetime]

class CreateUserRequest(BaseModel):
    email: str
    role:  str

class UpdateUserRequest(BaseModel):
    role:   Optional[str] = None
    active: Optional[bool] = None

class ThresholdConfig(BaseModel):
    stockout_alert_pct:   float = 10.0   # % of forecast
    low_stock_days:       float = 2.0    # days of demand
    forecast_spike_pct:   float = 50.0   # % above average

class PipelineStatusRow(BaseModel):
    job_name:       str
    started_at:     Optional[datetime]
    completed_at:   Optional[datetime]
    status:         str
    rows_processed: int
    error_message:  str

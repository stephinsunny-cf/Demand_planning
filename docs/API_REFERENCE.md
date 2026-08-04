# API Reference

The backend is built with FastAPI. All endpoints (except public/health ones) require a Supabase JWT passed as `Authorization: Bearer <token>`.

## Auth & Users (`/api/auth`)
- `GET /api/auth/profile`
  - Returns the current user's role (`super_admin`, `admin`, `viewer`, etc.) and whether they need to reset their password.

## Sales & Analytics (`/api/sales`)
- `GET /api/sales`
  - Fetches detailed **Kitchen Consumption** (SupplyNote) data.
  - Params: `start_date`, `end_date`, `brand`, `outlet`, `city`, `sku`.
- `GET /api/sales/summary`
  - Fetches KPIs for Kitchen Consumption (Total Qty, Unique SKUs).
- `GET /api/sales/pos`
  - Fetches detailed **Dish Sales** (UrbanPiper) data.
- `GET /api/sales/pos/summary`
  - Fetches KPIs for Dish Sales (Revenue, Orders, Avg Order Value).

## Forecasting (`/api/forecast`)
- `GET /api/forecast`
  - Fetches the latest generated demand forecasts.

## Reports (`/api/reports`)
- `GET /api/reports/variance`
  - Fetches discrepancies between actual consumption and recipe-based expected consumption.

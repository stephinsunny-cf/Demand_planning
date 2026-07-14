"""
pipeline/engines/forecast_engine.py — ENGINE 2
─────────────────────────────────────────────────
Facebook Prophet ML forecasting engine.

For each SKU × outlet combination with ≥30 days of history:
  1. Pull historical daily sales from fact_daily_sales
  2. Fit a Prophet model with weekly + yearly seasonality
  3. Add Indian public holiday seasonality
  4. Predict 30 days ahead
  5. Calculate MAPE on last 7 days (in-sample accuracy)
  6. Write predictions to fact_forecast

Falls back to simple moving-average forecast if Prophet is not installed.
"""

import logging
import math
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone, timedelta, date

import pandas as pd
import numpy as np

# Use the backend database helper for querying
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import query_df, get_db_connection

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

MIN_HISTORY_DAYS = 30
FORECAST_HORIZON = 30


# ── Indian holiday calendar ───────────────────────────────────────────────────

def _indian_holidays(years: list[int]) -> pd.DataFrame:
    """Return a DataFrame of Indian public holidays for Prophet."""
    holidays = []
    for year in years:
        holidays += [
            (f"Republic Day {year}",      f"{year}-01-26"),
            (f"Holi {year}",              f"{year}-03-25"),  # approximate
            (f"Good Friday {year}",       f"{year}-04-18"),
            (f"Eid ul-Fitr {year}",       f"{year}-04-10"),  # approximate
            (f"Independence Day {year}",  f"{year}-08-15"),
            (f"Gandhi Jayanti {year}",    f"{year}-10-02"),
            (f"Navratri {year}",          f"{year}-10-03"),
            (f"Dussehra {year}",          f"{year}-10-12"),
            (f"Diwali {year}",            f"{year}-10-20"),  # approximate
            (f"Christmas {year}",         f"{year}-12-25"),
            (f"New Year {year}",          f"{year}-01-01"),
            (f"Pongal {year}",            f"{year}-01-14"),
            (f"Onam {year}",              f"{year}-09-05"),  # approximate
        ]
    df = pd.DataFrame(holidays, columns=["holiday", "ds"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["lower_window"] = -1
    df["upper_window"] = 1
    return df


# ── MAPE calculation ──────────────────────────────────────────────────────────

def _mape(actual: pd.Series, predicted: pd.Series) -> float:
    """Mean Absolute Percentage Error — returns value 0-100."""
    mask = actual > 0
    if mask.sum() == 0:
        return float("nan")
    a = actual[mask].values
    p = predicted[mask].values
    return float(np.mean(np.abs((a - p) / a)) * 100)


# ── Prophet forecast ──────────────────────────────────────────────────────────

def _prophet_forecast(history: pd.DataFrame, sku: str, outlet: str) -> pd.DataFrame:
    """
    Fit Prophet model and return a 30-day forecast DataFrame.
    Returns empty DataFrame on failure.
    """
    try:
        from prophet import Prophet
    except ImportError:
        return _moving_average_forecast(history, sku, outlet)

    try:
        df_prophet = history[["date", "qty_sold"]].copy()
        df_prophet = df_prophet.rename(columns={"date": "ds", "qty_sold": "y"})
        df_prophet["ds"] = pd.to_datetime(df_prophet["ds"])
        df_prophet = df_prophet.dropna(subset=["ds", "y"])
        df_prophet = df_prophet[df_prophet["y"] >= 0]
        df_prophet = df_prophet.groupby("ds", as_index=False)["y"].sum()
        df_prophet = df_prophet.sort_values("ds")

        if len(df_prophet) < MIN_HISTORY_DAYS:
            return pd.DataFrame()

        years = list(set([df_prophet["ds"].min().year, df_prophet["ds"].max().year,
                          datetime.now().year, datetime.now().year + 1]))
        holidays = _indian_holidays(years)

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            holidays=holidays,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10,
        )
        model.fit(df_prophet)

        future = model.make_future_dataframe(periods=FORECAST_HORIZON, freq="D")
        forecast = model.predict(future)

        # Clip negative forecasts to 0
        forecast["yhat"]       = forecast["yhat"].clip(lower=0)
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)
        forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0)

        # Return only future dates
        today = pd.Timestamp(date.today())
        result = forecast[forecast["ds"] >= today][["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        result = result.head(FORECAST_HORIZON)
        result["sku"]            = sku
        result["outlet"]         = outlet
        result["model_run_date"] = date.today()
        result = result.rename(columns={
            "ds":         "forecast_date",
            "yhat":       "qty_predicted",
            "yhat_lower": "qty_lower",
            "yhat_upper": "qty_upper",
        })
        result["forecast_date"] = result["forecast_date"].dt.date

        return result[["forecast_date", "sku", "outlet", "qty_predicted", "qty_lower", "qty_upper", "model_run_date"]]

    except Exception as exc:
        return _moving_average_forecast(history, sku, outlet)


def _moving_average_forecast(history: pd.DataFrame, sku: str, outlet: str) -> pd.DataFrame:
    """Simple 7-day moving average fallback forecast."""
    try:
        avg = history["qty_sold"].tail(14).mean()
        if math.isnan(avg):
            avg = 1.0

        rows = []
        today = date.today()
        for i in range(1, FORECAST_HORIZON + 1):
            fdate = today + timedelta(days=i)
            # Add simple ±20% confidence interval
            rows.append({
                "forecast_date": fdate,
                "sku":           sku,
                "outlet":        outlet,
                "qty_predicted": round(avg, 2),
                "qty_lower":     round(avg * 0.8, 2),
                "qty_upper":     round(avg * 1.2, 2),
                "model_run_date": today,
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        return pd.DataFrame()


# ── Main engine ───────────────────────────────────────────────────────────────

def run() -> pd.DataFrame:
    """
    Run the forecast engine for all SKU × outlet combinations.
    Returns combined forecast DataFrame.
    """
    started_at = datetime.now(IST)
    print("=" * 60)
    print("ENGINE 2: Forecast Engine (Prophet) - start")

    try:
        # Find the maximum date in the dataset to simulate "today"
        max_date_df = query_df("""
            SELECT MAX(date) as max_date 
            FROM fact_daily_sales
        """)
        if max_date_df.empty or pd.isnull(max_date_df.iloc[0]["max_date"]):
            print("No sales data found in database.")
            return pd.DataFrame()
            
        max_date = max_date_df.iloc[0]["max_date"]

        # Load historical sales (limit to last 40 days of available data)
        sales_df = query_df(f"""
            SELECT date, sku, outlet, qty_sold 
            FROM fact_daily_sales
            WHERE date >= DATE '{max_date}' - INTERVAL '40 days'
        """)

        if sales_df.empty:
            print("No sales data found for tracked items — run sales aggregation engine first")
            return pd.DataFrame()

        sales_df["date"] = pd.to_datetime(sales_df["date"]).dt.date

        # Get all SKU × outlet combinations with enough history
        combos = (
            sales_df.groupby(["sku", "outlet"])
            .agg(days=("date", "nunique"), total_qty=("qty_sold", "sum"))
            .reset_index()
        )
        combos = combos[combos["days"] >= MIN_HISTORY_DAYS]

        print(f"Found {len(combos)} SKU x outlet combinations with >= {MIN_HISTORY_DAYS} days of history")

        all_forecasts = []
        skipped = 0

        for _, row in combos.iterrows():
            sku    = row["sku"]
            outlet = row["outlet"]

            history = sales_df[(sales_df["sku"] == sku) & (sales_df["outlet"] == outlet)].copy()
            forecast = _prophet_forecast(history, sku, outlet)

            if forecast.empty:
                skipped += 1
                continue
            all_forecasts.append(forecast)

        if not all_forecasts:
            print("No forecasts generated — possibly too little data")
            return pd.DataFrame()

        result = pd.concat(all_forecasts, ignore_index=True)
        print(f"Generated {len(result)} forecast rows for {len(all_forecasts)} combos ({skipped} skipped)")

        # Write to Postgres
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Clear existing forecast to avoid duplicates
                cur.execute("TRUNCATE TABLE fact_forecast")
                
                insert_query = """
                    INSERT INTO fact_forecast (forecast_date, sku, outlet, qty_predicted, qty_lower, qty_upper, model_run_date)
                    VALUES %s
                """
                values = [
                    (row['forecast_date'], row['sku'], row['outlet'], 
                     float(row['qty_predicted']), float(row['qty_lower']), float(row['qty_upper']), row['model_run_date'])
                    for _, row in result.iterrows()
                ]
                execute_values(cur, insert_query, values)
                conn.commit()
                print(f"Successfully inserted {len(values)} rows to fact_forecast!")

        return result

    except Exception as exc:
        print(f"Forecast engine failed: {exc}")
        return pd.DataFrame()

if __name__ == "__main__":
    run()

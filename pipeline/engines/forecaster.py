import os
import pandas as pd
import numpy as np
from datetime import timedelta
from backend.database import query_df as pg_query_df
from dotenv import load_dotenv

try:
    from prophet import Prophet
except ImportError:
    Prophet = None

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    ExponentialSmoothing = None

import warnings
warnings.filterwarnings("ignore")

load_dotenv()


def mape(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100


def run_forecast():
    """Run demand forecast using PostgreSQL data only."""
    print("Connecting to PostgreSQL...")
    from pipeline.loaders.postgres import insert_df as pg_insert_df

    print("Fetching historical sales data...")
    df = pg_query_df(
        "SELECT date, sku, outlet, sum(qty_sold) as qty "
        "FROM fact_daily_sales "
        "GROUP BY date, sku, outlet "
        "ORDER BY date"
    )
    if df.empty:
        print("No historical data found in fact_daily_sales. Exiting.")
        return

    df["date"] = pd.to_datetime(df["date"])
    max_date = df["date"].max()
    run_date = max_date.date()
    print(f"Latest data point: {run_date}")

    # Custom holidays (optional — skip gracefully if table missing)
    holidays_df = None
    try:
        h = pg_query_df("SELECT event_name as holiday, event_date as ds FROM custom_events")
        if not h.empty:
            h["ds"] = pd.to_datetime(h["ds"])
            holidays_df = h
    except Exception:
        pass

    # Top 100 SKU-Outlet combos by volume (last 30 days)
    t30 = max_date - timedelta(days=30)
    top100 = set(
        tuple(x) for x in df[df["date"] >= t30]
        .groupby(["sku", "outlet"])["qty"].sum()
        .reset_index()
        .sort_values("qty", ascending=False)
        .head(100)[["sku", "outlet"]].values
    )

    # Active combos (any sales in last 45 days)
    t45 = max_date - timedelta(days=45)
    active = set(
        (s, o) for (s, o), v in
        df[df["date"] >= t45].groupby(["sku", "outlet"])["qty"].sum().items()
        if v > 0
    )

    forecast_results = []
    print(f"Found {len(active)} active SKU-Outlet combinations.")

    count = 0
    for (sku, outlet), group in df.groupby(["sku", "outlet"]):
        if (sku, outlet) not in active:
            continue
        count += 1
        if count % 100 == 0:
            print(f"  Processed {count} items...")

        ts = group.set_index("date")["qty"].resample("D").sum().fillna(0).reset_index()

        def add_row(f_date, qty, model, mape_val=50.0):
            qty = max(0.0, float(qty))
            forecast_results.append({
                "forecast_date": f_date,
                "sku": sku,
                "outlet": outlet,
                "qty_predicted": round(qty, 2),
                "qty_lower": round(qty * 0.8, 2),
                "qty_upper": round(qty * 1.2, 2),
                "model_run_date": run_date,
                "model_name": model,
                "mape_7d": round(mape_val, 2),
            })

        # --- Very new items: simple 7-day moving average ---
        if len(ts) < 21:
            pred = ts["qty"].tail(7).mean() if len(ts) > 0 else 0
            for i in range(1, 15):
                add_row(run_date + timedelta(days=i), pred, "SMA_7D")
            continue

        used_prophet = False
        if (sku, outlet) in top100 and Prophet is not None:
            try:
                p_df = ts.rename(columns={"date": "ds", "qty": "y"})
                m = Prophet(holidays=holidays_df, daily_seasonality=False, yearly_seasonality=False)
                m.fit(p_df)
                future = m.make_future_dataframe(periods=14)
                fc = m.predict(future)
                merged = p_df.tail(7).merge(fc[["ds", "yhat"]], on="ds")
                acc = mape(merged["y"], merged["yhat"])
                for _, row in fc[fc["ds"] > pd.to_datetime(max_date)].head(14).iterrows():
                    add_row(row["ds"].date(), row["yhat"], "Prophet_v1", acc)
                used_prophet = True
            except Exception:
                pass

        if not used_prophet:
            try:
                ts_data = ts["qty"].values
                model_name = "HoltWinters_v1"
                if ExponentialSmoothing is not None and len(ts_data) >= 14:
                    hw = ExponentialSmoothing(
                        ts_data, seasonal_periods=7,
                        trend=None, seasonal="add",
                        initialization_method="estimated"
                    )
                    res = hw.fit()
                    preds = list(res.forecast(14))
                    acc = mape(ts_data[-7:], res.fittedvalues[-7:])
                else:
                    preds = [ts["qty"].ewm(span=7).mean().iloc[-1]] * 14
                    acc = 50.0
                    model_name = "EWMA_7D"

                for i, p in enumerate(preds):
                    add_row(run_date + timedelta(days=i + 1), p, model_name, acc)
            except Exception:
                pass

    if forecast_results:
        print(f"Generated {len(forecast_results)} forecast rows. Writing to PostgreSQL...")
        pg_insert_df(pd.DataFrame(forecast_results), "fact_forecast")
        print("Forecasting Engine complete.")
    else:
        print("No forecasts generated.")


if __name__ == "__main__":
    run_forecast()

"""
pipeline/run_prophet_backtest_v2.py
─────────────────────────────────────
Full-scale (no sampling) rolling-origin, out-of-sample backtest of Prophet
across Feb-April 2026, mirroring pipeline/run_lightgbm_backtest_v2.py's
fold structure exactly so both models are scored on the identical
combos/dates for a fair comparison.

Uses the SAME Prophet configuration as production (pipeline/engines/
forecast_engine.py): weekly seasonality, no yearly/daily seasonality, the
same Indian holiday calendar, changepoint_prior_scale=0.05,
seasonality_prior_scale=10, uncertainty_samples=0, MIN_HISTORY_DAYS=30.
Parallelized the same way production does (pebble ProcessPool, per-combo
timeout with moving-average fallback) so this is a fair test of what
Prophet actually does today, not a hobbled version of it.

Note: forecast_engine.py's own _prophet_forecast() can't be reused directly
for backtesting — it hardcodes date.today() to split historical/future rows,
which only makes sense for a live production run, not a simulated past
cutoff. This file reimplements the same Prophet config with an explicit
train_cutoff parameter instead.

Usage:
    python pipeline/run_prophet_backtest_v2.py
"""
import os
import sys
import time
import math
import logging
import concurrent.futures
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from pebble import ProcessPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import query_df, close_all_connections

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(message)s")
log = logging.getLogger("prophet_backtest_v2")

IST = timezone(timedelta(hours=5, minutes=30))
MIN_HISTORY_DAYS = 30
LOOKBACK_DAYS = 120

# Same fold structure as run_lightgbm_backtest_v2.py — Feb-April 2026,
# spans enough real history (data starts 2026-01-02) and covers 3 real
# holidays: Holi (fold 8), Eid ul-Fitr approx (fold 10), Good Friday approx (fold 11).
FOLDS = [
    (date(2026, 2, 3),  date(2026, 2, 4),  date(2026, 2, 9)),
    (date(2026, 2, 10), date(2026, 2, 11), date(2026, 2, 16)),
    (date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 23)),
    (date(2026, 2, 24), date(2026, 2, 25), date(2026, 3, 2)),
    (date(2026, 3, 3),  date(2026, 3, 4),  date(2026, 3, 9)),
    (date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 16)),
    (date(2026, 3, 17), date(2026, 3, 18), date(2026, 3, 23)),
    (date(2026, 3, 24), date(2026, 3, 25), date(2026, 3, 30)),  # includes Holi
    (date(2026, 3, 31), date(2026, 4, 1),  date(2026, 4, 6)),
    (date(2026, 4, 7),  date(2026, 4, 8),  date(2026, 4, 13)),  # includes Eid ul-Fitr (approx)
    (date(2026, 4, 14), date(2026, 4, 15), date(2026, 4, 20)),  # includes Good Friday (approx)
    (date(2026, 4, 21), date(2026, 4, 22), date(2026, 4, 27)),
]


def _indian_holidays(years: list) -> pd.DataFrame:
    """Identical calendar to forecast_engine.py's _indian_holidays()."""
    holidays = []
    for year in years:
        holidays += [
            (f"Republic Day {year}",      f"{year}-01-26"),
            (f"Holi {year}",              f"{year}-03-25"),
            (f"Good Friday {year}",       f"{year}-04-18"),
            (f"Eid ul-Fitr {year}",       f"{year}-04-10"),
            (f"Independence Day {year}",  f"{year}-08-15"),
            (f"Gandhi Jayanti {year}",    f"{year}-10-02"),
            (f"Navratri {year}",          f"{year}-10-03"),
            (f"Dussehra {year}",          f"{year}-10-12"),
            (f"Diwali {year}",            f"{year}-10-20"),
            (f"Christmas {year}",         f"{year}-12-25"),
            (f"New Year {year}",          f"{year}-01-01"),
            (f"Pongal {year}",            f"{year}-01-14"),
            (f"Onam {year}",              f"{year}-09-05"),
        ]
    df = pd.DataFrame(holidays, columns=["holiday", "ds"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["lower_window"] = -1
    df["upper_window"] = 1
    return df


def _prophet_fit_predict(history: pd.DataFrame, sku: str, outlet: str, train_cutoff: date, pred_start: date, pred_end: date) -> pd.DataFrame:
    """Fit Prophet on history <= train_cutoff, return predictions for [pred_start, pred_end]."""
    try:
        from prophet import Prophet
    except ImportError:
        return _moving_average(history, sku, outlet, pred_start, pred_end)

    try:
        df_p = history[["date", "qty_sold"]].copy()
        df_p = df_p.rename(columns={"date": "ds", "qty_sold": "y"})
        df_p["ds"] = pd.to_datetime(df_p["ds"])
        df_p = df_p.groupby("ds", as_index=False)["y"].sum().sort_values("ds")

        if len(df_p) < MIN_HISTORY_DAYS:
            return pd.DataFrame()

        years = sorted(set([df_p["ds"].min().year, df_p["ds"].max().year]))
        holidays = _indian_holidays(years)

        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            holidays=holidays,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10,
            uncertainty_samples=0,
        )
        model.fit(df_p)

        horizon = (pred_end - train_cutoff).days
        future = model.make_future_dataframe(periods=horizon, freq="D")
        forecast = model.predict(future)
        forecast["yhat"] = forecast["yhat"].clip(lower=0)

        mask = (forecast["ds"].dt.date >= pred_start) & (forecast["ds"].dt.date <= pred_end)
        result = forecast[mask][["ds", "yhat"]].copy()
        result["sku"] = sku
        result["outlet"] = outlet
        result = result.rename(columns={"ds": "date", "yhat": "qty_predicted"})
        result["date"] = result["date"].dt.date
        return result[["date", "sku", "outlet", "qty_predicted"]]

    except Exception:
        return _moving_average(history, sku, outlet, pred_start, pred_end)


def _moving_average(history: pd.DataFrame, sku: str, outlet: str, pred_start: date, pred_end: date) -> pd.DataFrame:
    try:
        avg = history["qty_sold"].tail(14).mean()
        if math.isnan(avg):
            avg = 1.0
        rows = []
        d = pred_start
        while d <= pred_end:
            rows.append({"date": d, "sku": sku, "outlet": outlet, "qty_predicted": round(avg, 2)})
            d += timedelta(days=1)
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def load_data() -> pd.DataFrame:
    log.info("Loading fact_daily_sales for tracked combos (Feb-April window + lookback)...")
    df = query_df("""
        SELECT date, sku_code AS sku, outlet, qty_sold
        FROM fact_daily_sales
        WHERE date >= '2026-01-01' AND date <= '2026-04-27'
          AND sku_code IN (SELECT code FROM procurement_tracker)
    """)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.groupby(["date", "sku", "outlet"], as_index=False)["qty_sold"].sum()
    log.info(f"Loaded {len(df):,} raw rows across {df[['sku','outlet']].drop_duplicates().shape[0]:,} combos.")
    return df


def run_fold(df: pd.DataFrame, train_cutoff: date, pred_start: date, pred_end: date, fold_num: int) -> pd.DataFrame:
    t0 = time.time()
    hist_start = train_cutoff - timedelta(days=LOOKBACK_DAYS)
    hist = df[(df["date"] >= hist_start) & (df["date"] <= train_cutoff)]

    combos = (
        hist.groupby(["sku", "outlet"])
        .agg(days=("date", "nunique"))
        .reset_index()
    )
    combos = combos[combos["days"] >= MIN_HISTORY_DAYS]
    log.info(f"Fold {fold_num}/{len(FOLDS)}: train<={train_cutoff}, {len(combos):,} combos with >= {MIN_HISTORY_DAYS}d history")

    args_list = []
    for _, row in combos.iterrows():
        sku, outlet = row["sku"], row["outlet"]
        combo_hist = hist[(hist["sku"] == sku) & (hist["outlet"] == outlet)]
        args_list.append((combo_hist, sku, outlet, train_cutoff, pred_start, pred_end))

    max_workers = max(os.cpu_count() - 1, 1) if os.cpu_count() else 1
    close_all_connections()

    all_forecasts = []
    skipped = 0
    timeout_fallbacks = 0

    with ProcessPool(max_workers=max_workers) as pool:
        future_to_args = {}
        for arg in args_list:
            future = pool.schedule(_prophet_fit_predict, args=arg, timeout=15)
            future_to_args[future] = arg

        for future in concurrent.futures.as_completed(future_to_args.keys()):
            arg = future_to_args[future]
            try:
                forecast = future.result()
                if forecast.empty:
                    skipped += 1
                else:
                    all_forecasts.append(forecast)
            except concurrent.futures.TimeoutError:
                timeout_fallbacks += 1
                fb = _moving_average(arg[0], arg[1], arg[2], pred_start, pred_end)
                if not fb.empty:
                    all_forecasts.append(fb)
                else:
                    skipped += 1
            except Exception:
                skipped += 1

    elapsed = time.time() - t0
    if not all_forecasts:
        log.warning(f"Fold {fold_num}: no forecasts generated.")
        return pd.DataFrame()

    result = pd.concat(all_forecasts, ignore_index=True)
    log.info(f"Fold {fold_num}/{len(FOLDS)} done in {elapsed:.1f}s | {len(result):,} predicted rows | "
              f"skipped={skipped} timeout_fallbacks={timeout_fallbacks}")
    return result


def main():
    log.info("=" * 70)
    log.info("Prophet Full-Scale Rolling-Origin Backtest (Feb-April 2026)")
    log.info("=" * 70)

    df = load_data()

    all_scored = []
    for i, (train_cutoff, pred_start, pred_end) in enumerate(FOLDS, start=1):
        pred = run_fold(df, train_cutoff, pred_start, pred_end, i)
        if pred.empty:
            continue
        actual = df[(df["date"] >= pred_start) & (df["date"] <= pred_end)]
        scored = pred.merge(actual, on=["sku", "outlet", "date"])
        all_scored.append(scored[["date", "sku", "outlet", "qty_predicted", "qty_sold"]])

    result = pd.concat(all_scored, ignore_index=True)
    total_sales = result["qty_sold"].sum()
    total_error = (result["qty_predicted"] - result["qty_sold"]).abs().sum()
    accuracy = 100.0 * (1 - total_error / total_sales)

    log.info("=" * 70)
    log.info("PROPHET FULL-SCALE BACKTEST RESULT (Feb-April 2026, out-of-sample)")
    log.info("=" * 70)
    log.info(f"Total Intersection Sales:   {total_sales:,.2f}")
    log.info(f"Prophet Out-of-Sample Error: {total_error:,.2f}")
    log.info(f"Prophet Accuracy:            {accuracy:.2f}%")
    log.info("=" * 70)


if __name__ == "__main__":
    main()

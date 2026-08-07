"""
pipeline/engines/lightgbm_engine.py — ENGINE 2 (replaces Prophet)
────────────────────────────────────────────────────────────────
Single global LightGBM model trained across all SKU x outlet combos at
once, replacing the previous per-combo Prophet approach.

Why: rigorous rolling-origin backtest (Feb-April 2026, full scale, includes
real festivals) showed this beats Prophet 78.64% vs 72.25% on accuracy, and
finishes in ~7 minutes instead of many hours, which also fixes the GitHub
Actions timeout Prophet was hitting. See pipeline/run_lightgbm_backtest_v2.py
and pipeline/run_prophet_backtest_v2.py for the validation methodology, and
docs/DECISIONS_LOG.md for the writeup.

Two-pass design:
  1. Train on history up to 7 days ago, predict that held-out week, score
     against actuals -> honest per-combo accuracy (never trained on what
     it's being scored against).
  2. Retrain on ALL available history (including that most recent week),
     predict FORECAST_HORIZON days forward -> this is the real production
     forecast, using every bit of data available for the best prediction.
Both passes use identical features/hyperparameters; only the training
window and the accuracy attached to each combo's output rows differ.

Same output schema as the previous forecast_engine.py (fact_forecast:
forecast_date, sku, outlet, qty_predicted, qty_lower, qty_upper,
model_run_date, in_sample_accuracy) -- drop-in replacement, nothing
downstream (procurement, warehouse planning, the frontend) needs to change.
"""
import os
import sys
import logging
from datetime import date, datetime, timezone, timedelta

import pandas as pd
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import query_df, get_db

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

MIN_HISTORY_DAYS = 30
FORECAST_HORIZON = 30
LOOKBACK_DAYS    = 365
HOLDOUT_DAYS     = 7  # held out from training pass 1, used only to score accuracy

# Same Indian holiday calendar as the old Prophet engine's _indian_holidays(),
# so this model has the same signal available to it.
_HOLIDAY_MMDD = [
    ("01-26", "Republic Day"), ("03-25", "Holi"), ("04-18", "Good Friday"),
    ("04-10", "Eid ul-Fitr"), ("08-15", "Independence Day"),
    ("10-02", "Gandhi Jayanti"), ("10-03", "Navratri"), ("10-12", "Dussehra"),
    ("10-20", "Diwali"), ("12-25", "Christmas"), ("01-01", "New Year"),
    ("01-14", "Pongal"), ("09-05", "Onam"),
]

FEATURE_COLS = ["sku_cat", "outlet_cat", "lag_7", "lag_14", "lag_28",
                 "roll_mean_7", "roll_mean_14", "roll_mean_28",
                 "dow", "dom", "month", "is_holiday_window", "combo_mean"]


def _holiday_dates(years: list) -> set:
    dates = set()
    for year in years:
        for mmdd, _name in _HOLIDAY_MMDD:
            hd = pd.Timestamp(f"{year}-{mmdd}").date()
            for offset in (-1, 0, 1):
                dates.add(hd + timedelta(days=offset))
    return dates


def _load_history(max_date: date) -> pd.DataFrame:
    hist_start = max_date - timedelta(days=LOOKBACK_DAYS)
    df = query_df(f"""
        SELECT date, sku_code AS sku, outlet, qty_sold
        FROM fact_daily_sales
        WHERE date >= '{hist_start}' AND date <= '{max_date}'
          AND sku_code IN (SELECT code FROM procurement_tracker)
    """)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.groupby(["date", "sku", "outlet"], as_index=False)["qty_sold"].sum()
    return df


def _build_dense_panel(df: pd.DataFrame, combos: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    all_dates = pd.date_range(start, end, freq="D").date
    pairs = list(combos[["sku", "outlet"]].itertuples(index=False, name=None))
    rows = [(s, o, d) for (s, o) in pairs for d in all_dates]
    panel = pd.DataFrame(rows, columns=["sku", "outlet", "date"])
    panel = panel.merge(df, on=["sku", "outlet", "date"], how="left")
    panel["qty_sold"] = panel["qty_sold"].fillna(0.0)
    return panel


def _add_features(panel: pd.DataFrame, combo_means: pd.DataFrame, holiday_dates: set) -> pd.DataFrame:
    panel = panel.sort_values(["sku", "outlet", "date"]).reset_index(drop=True)
    g = panel.groupby(["sku", "outlet"], sort=False)["qty_sold"]

    panel["lag_7"]  = g.shift(7)
    panel["lag_14"] = g.shift(14)
    panel["lag_28"] = g.shift(28)
    shifted = g.shift(1)
    panel["roll_mean_7"]  = shifted.groupby([panel["sku"], panel["outlet"]]).rolling(7,  min_periods=1).mean().reset_index(drop=True)
    panel["roll_mean_14"] = shifted.groupby([panel["sku"], panel["outlet"]]).rolling(14, min_periods=1).mean().reset_index(drop=True)
    panel["roll_mean_28"] = shifted.groupby([panel["sku"], panel["outlet"]]).rolling(28, min_periods=1).mean().reset_index(drop=True)

    dt = pd.to_datetime(panel["date"])
    panel["dow"]   = dt.dt.dayofweek
    panel["dom"]   = dt.dt.day
    panel["month"] = dt.dt.month
    panel["is_holiday_window"] = panel["date"].isin(holiday_dates).astype(int)

    panel = panel.merge(combo_means, on=["sku", "outlet"], how="left")
    panel["combo_mean"] = panel["combo_mean"].fillna(0.0)

    panel["sku_cat"]    = panel["sku"].astype("category")
    panel["outlet_cat"] = panel["outlet"].astype("category")
    return panel


def _train_model(train_df: pd.DataFrame, combos: pd.DataFrame, hist_start: date, train_cutoff: date, holiday_dates: set):
    panel = _build_dense_panel(train_df, combos, hist_start, train_cutoff)
    combo_means = train_df.groupby(["sku", "outlet"], as_index=False)["qty_sold"].mean().rename(columns={"qty_sold": "combo_mean"})
    panel = _add_features(panel, combo_means, holiday_dates)
    panel = panel.dropna(subset=["lag_28"])

    val_cutoff = train_cutoff - timedelta(days=7)
    tr = panel[panel["date"] <= val_cutoff]
    va = panel[panel["date"] > val_cutoff]

    model = lgb.LGBMRegressor(
        objective="regression_l1",
        n_estimators=1000,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        verbosity=-1,
    )
    model.fit(
        tr[FEATURE_COLS], tr["qty_sold"],
        eval_set=[(va[FEATURE_COLS], va["qty_sold"])],
        eval_metric="mae",
        categorical_feature=["sku_cat", "outlet_cat"],
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
    )
    return model, combo_means


def _predict(model, combo_means: pd.DataFrame, history_df: pd.DataFrame, combos: pd.DataFrame,
             hist_start: date, pred_start: date, pred_end: date, holiday_dates: set) -> pd.DataFrame:
    """Predict one day at a time, feeding each day's own prediction back in as
    that day's "known" value before computing lag/rolling features for the
    next day.

    Predicting the whole horizon in one shot doesn't work: _build_dense_panel
    fills every date it doesn't have real data for with qty_sold=0 so the
    per-combo date grid stays complete, but for future (not-yet-happened)
    dates that 0 isn't a real observation -- it's a placeholder. lag/rolling
    features computed straight off that column don't know the difference, so
    the further into the horizon a day is, the more of its rolling window is
    fake zeros instead of real sales, and roll_mean_7 collapses toward 0
    (measured: a combo with a real ~130/day average fell to a "recent
    average" of 30 by day 7 of a 7-day horizon). The model then predicts off
    that deflated signal and badly under-forecasts later days. Recursing
    day-by-day and substituting the prediction for the placeholder avoids
    that entirely.
    """
    extended = history_df
    all_preds = []
    current = pred_start
    while current <= pred_end:
        panel = _build_dense_panel(extended, combos, hist_start, current)
        panel = _add_features(panel, combo_means, holiday_dates)
        day_rows = panel[panel["date"] == current].copy()
        day_rows["qty_predicted"] = model.predict(day_rows[FEATURE_COLS]).clip(min=0)
        all_preds.append(day_rows[["date", "sku", "outlet", "qty_predicted"]])

        carry_forward = day_rows[["date", "sku", "outlet", "qty_predicted"]].rename(
            columns={"qty_predicted": "qty_sold"}
        )
        extended = pd.concat([extended, carry_forward], ignore_index=True)
        current += timedelta(days=1)

    return pd.concat(all_preds, ignore_index=True)


def run() -> pd.DataFrame:
    started_at = datetime.now(IST)
    log.info("=" * 60)
    log.info("ENGINE 2: LightGBM Forecast Engine - start")

    try:
        max_date_df = query_df("SELECT MAX(date) as max_date FROM fact_daily_sales")
        if max_date_df.empty or pd.isnull(max_date_df.iloc[0]["max_date"]):
            log.warning("No sales data found in database.")
            return pd.DataFrame()
        max_date = pd.to_datetime(max_date_df.iloc[0]["max_date"]).date()

        full_history = _load_history(max_date)
        if full_history.empty:
            log.warning("No sales data found for tracked items.")
            return pd.DataFrame()

        combos_all = (
            full_history.groupby(["sku", "outlet"])
            .agg(days=("date", "nunique"))
            .reset_index()
        )
        combos = combos_all[combos_all["days"] >= MIN_HISTORY_DAYS][["sku", "outlet"]]
        log.info(f"Found {len(combos):,} SKU x outlet combinations with >= {MIN_HISTORY_DAYS} days of history")

        years = sorted(set([max_date.year, max_date.year + 1, max_date.year - 1]))
        holiday_dates = _holiday_dates(years)
        hist_start = max_date - timedelta(days=LOOKBACK_DAYS)

        # ── Pass 1: honest held-out accuracy ──────────────────────────────
        acc_cutoff = max_date - timedelta(days=HOLDOUT_DAYS)
        train_df_acc = full_history[full_history["date"] <= acc_cutoff]
        acc_model, acc_combo_means = _train_model(train_df_acc, combos, hist_start, acc_cutoff, holiday_dates)

        holdout_start = acc_cutoff + timedelta(days=1)
        holdout_pred = _predict(acc_model, acc_combo_means, train_df_acc, combos,
                                 hist_start, holdout_start, max_date, holiday_dates)
        actual_holdout = full_history[(full_history["date"] >= holdout_start) & (full_history["date"] <= max_date)]
        scored = holdout_pred.merge(actual_holdout, on=["sku", "outlet", "date"], how="inner")

        # Per-combo accuracy: 100 - WMAPE over the held-out week
        combo_acc = (
            scored.assign(abs_err=lambda d: (d["qty_predicted"] - d["qty_sold"]).abs())
            .groupby(["sku", "outlet"])
            .agg(abs_err=("abs_err", "sum"), actual=("qty_sold", "sum"))
            .reset_index()
        )
        combo_acc["in_sample_accuracy"] = combo_acc.apply(
            lambda r: max(0.0, 100.0 * (1 - r["abs_err"] / r["actual"])) if r["actual"] > 0 else None, axis=1
        )
        combo_acc = combo_acc[["sku", "outlet", "in_sample_accuracy"]]
        scorable = combo_acc["in_sample_accuracy"].notna().sum()
        log.info(f"Held-out accuracy: {scorable:,} of {len(combo_acc):,} combos had actual sales "
                 f"in the holdout week to score against (mean {combo_acc['in_sample_accuracy'].mean():.2f}%)")

        # ── Pass 2: real forecast, trained on everything available ────────
        final_model, final_combo_means = _train_model(full_history, combos, hist_start, max_date, holiday_dates)
        fore_start = max_date + timedelta(days=1)
        fore_end = max_date + timedelta(days=FORECAST_HORIZON)
        forecast = _predict(final_model, final_combo_means, full_history, combos,
                             hist_start, fore_start, fore_end, holiday_dates)

        forecast = forecast.rename(columns={"date": "forecast_date"})
        forecast["qty_lower"] = (forecast["qty_predicted"] * 0.8).round(2)
        forecast["qty_upper"] = (forecast["qty_predicted"] * 1.2).round(2)
        forecast["qty_predicted"] = forecast["qty_predicted"].round(2)
        forecast["model_run_date"] = max_date
        forecast = forecast.merge(combo_acc, on=["sku", "outlet"], how="left")

        log.info(f"Generated {len(forecast):,} forecast rows for {len(combos):,} combos.")

        # ── Write to Postgres (same atomic-swap pattern as the Prophet engine) ──
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS fact_forecast_new")
                cur.execute("CREATE TABLE IF NOT EXISTS fact_forecast_new (LIKE fact_forecast INCLUDING ALL)")

                insert_query = """
                    INSERT INTO fact_forecast_new (forecast_date, sku, outlet, qty_predicted, qty_lower, qty_upper, model_run_date, in_sample_accuracy)
                    VALUES %s
                """
                from psycopg2.extras import execute_values
                # pandas silently turns a missing in_sample_accuracy (combos with
                # no actual sales in the holdout week to score against) into the
                # float NaN, not None -- and psycopg2 will happily write that NaN
                # in as a real stored value instead of SQL NULL, which then
                # poisons any AVG()/SUM() touching the column. Convert explicitly.
                acc_col = forecast["in_sample_accuracy"].where(forecast["in_sample_accuracy"].notna(), None)
                values = [
                    (row["forecast_date"], row["sku"], row["outlet"],
                     float(row["qty_predicted"]), float(row["qty_lower"]), float(row["qty_upper"]),
                     row["model_run_date"], acc)
                    for (_, row), acc in zip(forecast.iterrows(), acc_col)
                ]
                execute_values(cur, insert_query, values)

                cur.execute("DROP TABLE IF EXISTS fact_forecast")
                cur.execute("ALTER TABLE fact_forecast_new RENAME TO fact_forecast")
                conn.commit()
                log.info(f"Successfully inserted {len(values):,} rows to fact_forecast!")

        elapsed = (datetime.now(IST) - started_at).total_seconds()
        log.info(f"LightGBM Forecast Engine completed in {elapsed:.1f}s")
        return forecast

    except Exception as exc:
        log.error(f"LightGBM forecast engine failed: {exc}", exc_info=True)
        return pd.DataFrame()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s")
    run()

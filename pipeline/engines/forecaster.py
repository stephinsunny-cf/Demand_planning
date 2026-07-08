import os
import pandas as pd
import numpy as np
from datetime import timedelta
import clickhouse_connect
from dotenv import load_dotenv

# Optional heavy imports handled gracefully
try:
    from prophet import Prophet
except ImportError:
    Prophet = None

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    ExponentialSmoothing = None

import warnings
warnings.filterwarnings('ignore')

load_dotenv()

def mape(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    # Avoid division by zero
    mask = y_true != 0
    if not mask.any(): return 0.0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def run_forecast():
    print("Connecting to ClickHouse...")
    db = clickhouse_connect.get_client(
        host=os.getenv('LOCAL_HOST', 'localhost'),
        port=int(os.getenv('LOCAL_PORT', 8123)),
        username=os.getenv('LOCAL_USER', 'default'),
        password=os.getenv('LOCAL_PASSWORD', 'admin123'),
        database='demand_planning'
    )
    
    # Create required tables
    db.command("""
        CREATE TABLE IF NOT EXISTS custom_events (
            id UUID DEFAULT generateUUIDv4(),
            event_name String,
            event_date Date,
            outlet String
        ) ENGINE = MergeTree() ORDER BY event_date
    """)
    
    db.command("""
        CREATE TABLE IF NOT EXISTS fact_forecast (
            forecast_date Date,
            sku String,
            outlet String,
            qty_predicted Float64,
            qty_lower Float64,
            qty_upper Float64,
            model_run_date Date,
            model_name String,
            mape_7d Float64
        ) ENGINE = MergeTree() ORDER BY (forecast_date, sku, outlet)
    """)
    
    # 1. Fetch Actuals
    print("Fetching historical sales data...")
    query = """
        SELECT date, sku, outlet, sum(qty_sold) as qty
        FROM fact_daily_sales
        GROUP BY date, sku, outlet
        ORDER BY date
    """
    df = db.query_df(query)
    if df.empty:
        print("No historical data found. Exiting.")
        return
        
    df['date'] = pd.to_datetime(df['date'])
    max_date = df['date'].max()
    run_date = max_date.date()
    
    print(f"Latest data point: {run_date}")
    
    # Fetch custom holidays
    holidays_df = db.query_df("SELECT event_name as holiday, event_date as ds FROM custom_events")
    if not holidays_df.empty:
        holidays_df['ds'] = pd.to_datetime(holidays_df['ds'])
    else:
        holidays_df = None
        
    # 2. Identify Top 100 SKU-Outlets (trailing 30 days)
    t30_date = max_date - timedelta(days=30)
    t30_df = df[df['date'] >= t30_date]
    
    volume_df = t30_df.groupby(['sku', 'outlet'])['qty'].sum().reset_index()
    volume_df = volume_df.sort_values('qty', ascending=False)
    
    # Active SKUs (sold at least 1 item in last 45 days)
    t45_date = max_date - timedelta(days=45)
    active_mask = df['date'] >= t45_date
    active_combinations = df[active_mask].groupby(['sku', 'outlet'])['qty'].sum()
    active_combinations = active_combinations[active_combinations > 0].index.tolist()
    
    top_100_combos = set(tuple(x) for x in volume_df.head(100)[['sku', 'outlet']].values)
    
    forecast_results = []
    
    print(f"Found {len(active_combinations)} active SKU-Outlet combinations.")
    
    # Group data
    grouped = df.groupby(['sku', 'outlet'])
    
    count = 0
    for (sku, outlet), group in grouped:
        if (sku, outlet) not in active_combinations:
            continue
            
        count += 1
        if count % 100 == 0:
            print(f"Processed {count}/{len(active_combinations)} items...")
            
        # Resample to fill missing days with 0
        ts = group.set_index('date')['qty'].resample('D').sum().fillna(0).reset_index()
        
        if len(ts) < 21:
            # Fallback to simple moving average for very new items
            model_name = "SMA_7D"
            pred_val = ts['qty'].tail(7).mean() if len(ts) > 0 else 0
            
            # Predict next 14 days
            for i in range(1, 15):
                f_date = run_date + timedelta(days=i)
                forecast_results.append({
                    'forecast_date': f_date,
                    'sku': sku,
                    'outlet': outlet,
                    'qty_predicted': round(pred_val, 2),
                    'qty_lower': round(max(0, pred_val * 0.8), 2),
                    'qty_upper': round(pred_val * 1.2, 2),
                    'model_run_date': run_date,
                    'model_name': model_name,
                    'mape_7d': 50.0 # Placeholder for naive models
                })
            continue

        is_top_100 = (sku, outlet) in top_100_combos
        accuracy = 0.0
        
        if is_top_100 and Prophet is not None:
            model_name = "Prophet_v1"
            try:
                p_df = ts.rename(columns={'date': 'ds', 'qty': 'y'})
                m = Prophet(holidays=holidays_df, daily_seasonality=False, yearly_seasonality=False)
                m.fit(p_df)
                
                future = m.make_future_dataframe(periods=14)
                forecast = m.predict(future)
                
                # Calculate training MAPE on last 7 actuals
                merged = p_df.tail(7).merge(forecast[['ds', 'yhat']], on='ds')
                accuracy = mape(merged['y'], merged['yhat'])
                
                # Extract 14 day future
                future_f = forecast[forecast['ds'] > pd.to_datetime(max_date)].head(14)
                for _, row in future_f.iterrows():
                    forecast_results.append({
                        'forecast_date': row['ds'].date(),
                        'sku': sku,
                        'outlet': outlet,
                        'qty_predicted': round(max(0, row['yhat']), 2),
                        'qty_lower': round(max(0, row['yhat_lower']), 2),
                        'qty_upper': round(max(0, row['yhat_upper']), 2),
                        'model_run_date': run_date,
                        'model_name': model_name,
                        'mape_7d': round(accuracy, 2)
                    })
            except Exception as e:
                # Fallback on Prophet failure
                is_top_100 = False 

        if not is_top_100:
            model_name = "HoltWinters_v1"
            try:
                # Holt Winters fallback
                ts_data = ts['qty'].values
                if ExponentialSmoothing is not None and len(ts_data) >= 14:
                    hw = ExponentialSmoothing(ts_data, seasonal_periods=7, trend=None, seasonal='add', initialization_method="estimated")
                    res = hw.fit()
                    preds = res.forecast(14)
                    
                    # Calculate training MAPE
                    fitted = res.fittedvalues[-7:]
                    actuals = ts_data[-7:]
                    accuracy = mape(actuals, fitted)
                else:
                    # EWMA Pandas fallback
                    ewm = ts['qty'].ewm(span=7).mean().iloc[-1]
                    preds = [ewm] * 14
                    accuracy = 50.0
                    model_name = "EWMA_7D"
                    
                for i in range(14):
                    f_date = run_date + timedelta(days=i+1)
                    p_val = max(0, preds[i])
                    forecast_results.append({
                        'forecast_date': f_date,
                        'sku': sku,
                        'outlet': outlet,
                        'qty_predicted': round(p_val, 2),
                        'qty_lower': round(max(0, p_val * 0.8), 2),
                        'qty_upper': round(p_val * 1.2, 2),
                        'model_run_date': run_date,
                        'model_name': model_name,
                        'mape_7d': round(accuracy, 2)
                    })
            except Exception as e:
                pass # Skip cleanly on math errors

    if forecast_results:
        print(f"Generated {len(forecast_results)} forecast records. Inserting into database...")
        f_df = pd.DataFrame(forecast_results)
        
        # Clean up old predictions before inserting new ones
        db.command("TRUNCATE TABLE fact_forecast")
        db.insert_df("fact_forecast", f_df)
        print("Success! Forecasting Engine completed.")
    else:
        print("No forecasts generated.")

if __name__ == "__main__":
    run_forecast()

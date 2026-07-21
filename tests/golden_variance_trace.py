import pandas as pd
from backend.database import query_df

def trace():
    print('Checking fact_variance for CFTEST999 at Khichdi Tales Jlt...')
    df = query_df("""
        SELECT date, outlet, ingredient, expected_qty, actual_qty, variance_qty
        FROM fact_variance
        WHERE ingredient = 'CFTEST999'
          AND lower(trim(outlet)) = 'khichdi tales jlt'
        ORDER BY date DESC
    """)
    pd.set_option('display.max_columns', None)
    print(df)

if __name__ == '__main__':
    trace()

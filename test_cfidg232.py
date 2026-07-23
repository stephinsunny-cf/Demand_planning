from backend.database import query_df

print("Checking fact_variance for CFIDG232 at Khichdi Tales Jlt...")
df = query_df("""
    SELECT date, outlet, ingredient, expected_qty, actual_qty, variance_qty
    FROM fact_variance
    WHERE ingredient = 'CFIDG232'
      AND lower(trim(outlet)) = 'khichdi tales jlt'
    ORDER BY date DESC
""")
print(df)

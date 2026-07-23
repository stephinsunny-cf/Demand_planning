from backend.database import get_db_connection
with get_db_connection() as conn:
    with conn.cursor() as cur:
        # MongoDB ObjectIds are 24 character hex strings
        cur.execute("DELETE FROM alerts WHERE length(outlet) = 24 AND outlet ~ '^[0-9a-f]{24}$'")
        deleted = cur.rowcount
    conn.commit()
print(f'Deleted {deleted} alerts with raw MongoDB IDs.')

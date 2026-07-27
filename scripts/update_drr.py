import psycopg2, os, math
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

def round_up_moq(qty, moq):
    if moq <= 0: moq = 1.0
    if qty <= 0: return 0.0
    return math.ceil(qty / moq) * moq

def main():
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST'), 
        database=os.getenv('PG_DB'), 
        user=os.getenv('PG_USER'), 
        password=os.getenv('PG_PASS'), 
        port=os.getenv('PG_PORT')
    )
    conn.autocommit = False
    cur = conn.cursor()
    
    print("Fetching tracked items...")
    cur.execute("SELECT code, lead_time_days FROM procurement_tracker")
    tracked_items = cur.fetchall()
    tracked_dict = {code: float(lt) if lt else 7.0 for code, lt in tracked_items}
    
    print("Calculating DRR...")
    cur.execute("""
        SELECT sku_code, SUM(qty_sold) / 30.0
        FROM fact_daily_sales
        WHERE date >= (SELECT MAX(date) - INTERVAL '30 days' FROM fact_daily_sales)
          AND sku_code IN (SELECT code FROM procurement_tracker)
        GROUP BY sku_code
    """)
    drr_dict = {row[0]: float(row[1]) for row in cur.fetchall()}
    
    print("Calculating WH SIH...")
    cur.execute("""
        SELECT ingredient, SUM(qty_available)
        FROM fact_kitchen_stock
        WHERE (lower(kitchen) LIKE '%warehouse%' OR lower(kitchen) LIKE '% wh %' OR lower(kitchen) LIKE '%_wh%')
          AND ingredient IN (SELECT code FROM procurement_tracker)
        GROUP BY ingredient
    """)
    wh_sih_dict = {row[0]: float(row[1]) for row in cur.fetchall()}
    
    print("Calculating Open POs...")
    cur.execute("""
        SELECT ingredient, SUM(qty_ordered)
        FROM fact_open_pos
        WHERE status = 'open'
          AND ingredient IN (SELECT code FROM procurement_tracker)
        GROUP BY ingredient
    """)
    open_po_dict = {row[0]: float(row[1]) for row in cur.fetchall()}
    
    print("Updating database...")
    updates = []
    for code, lead_time in tracked_dict.items():
        drr = drr_dict.get(code, 0.0)
        wh_sih = wh_sih_dict.get(code, 0.0)
        open_po = open_po_dict.get(code, 0.0)
        
        safety_buffer = drr * lead_time
        net_requirement = max((drr * 7.0) - wh_sih, 0)
        raw_qty = (net_requirement + safety_buffer) - open_po
        neworder = round_up_moq(raw_qty, 1.0)
        
        updates.append((drr, wh_sih, open_po, neworder, code))
        
    execute_values(cur, """
        UPDATE procurement_tracker AS pt
        SET drr = v.drr,
            wh_sih = v.wh_sih,
            open_po = v.open_po,
            neworder = v.neworder
        FROM (VALUES %s) AS v(drr, wh_sih, open_po, neworder, code)
        WHERE pt.code = v.code
    """, updates)
    
    conn.commit()
    conn.close()
    print("Success!")

if __name__ == '__main__':
    main()

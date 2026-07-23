import os, sys
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from psycopg2.extras import execute_values

# add root to sys.path so we can import backend
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.database import get_db_connection

load_dotenv(r'd:\demand-planning\.env')

print('Fetching outlets from API...')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto('https://www.supplynote.in/signin')
    page.fill('input[name="username"], input[placeholder*="username" i]', os.getenv('SUPPLYNOTE_USER'))
    page.fill('input[type="password"]', os.getenv('SUPPLYNOTE_PASSWORD'))
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: '/signin' not in url, timeout=25000)
    
    outlets = page.evaluate('''async () => {
        let res = await fetch('/api/outlets', {headers: {'Accept': 'application/json'}});
        let json = await res.json();
        return json.data || json || [];
    }''')
    browser.close()

mapping = {}
for out in outlets:
    if '_id' in out and 'name' in out:
        mapping[out['_id']] = out['name']

print(f'Found {len(mapping)} mappings. Updating DB...')

with get_db_connection() as conn:
    with conn.cursor() as cur:
        # Update fact_kitchen_stock
        updated_stock = 0
        for _id, name in mapping.items():
            cur.execute('UPDATE fact_kitchen_stock SET kitchen = %s WHERE kitchen = %s', (name, _id))
            updated_stock += cur.rowcount
            
        # Update alerts
        cur.execute("SELECT alert_id, message, outlet FROM alerts WHERE alert_type = 'KITCHEN_STOCKOUT'")
        alerts = cur.fetchall()
        updated_alerts = 0
        for alert_id, msg, outlet in alerts:
            if outlet in mapping:
                real_name = mapping[outlet]
                new_msg = msg.replace(outlet, real_name)
                cur.execute('UPDATE alerts SET outlet = %s, message = %s WHERE alert_id = %s', (real_name, new_msg, alert_id))
                updated_alerts += 1
                
    conn.commit()

print(f'Done! Updated {updated_stock} rows in fact_kitchen_stock and {updated_alerts} alerts.')

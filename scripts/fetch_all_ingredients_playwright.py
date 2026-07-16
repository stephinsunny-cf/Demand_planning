import os
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("playwright_downloader")

# Load .env if it exists (local dev). On GitHub Actions, env vars are injected directly.
load_dotenv()
SN_USERNAME = os.getenv('SUPPLYNOTE_USER')
SN_PASSWORD = os.getenv('SUPPLYNOTE_PASSWORD')
BUSINESS_ID = "65b205675255c93a41dd7849"

# DROPZONE_DIR env var is set in the GitHub Actions workflow.
# Falls back to a local path for development.
DROPZONE = os.getenv(
    'DROPZONE_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'supplynote_dropzone')
)
os.makedirs(DROPZONE, exist_ok=True)

import argparse

def run(yesterday_only=False):
    # Parse CLI args only if not called from the FastAPI background task
    import sys
    if not yesterday_only and len(sys.argv) > 1 and '--yesterday' in sys.argv:
        yesterday_only = True

    if yesterday_only:
        yesterday = datetime.now() - timedelta(days=1)
        start_date = datetime(yesterday.year, yesterday.month, yesterday.day)
        end_date = start_date
        log.info(f"Cron mode: Fetching only yesterday's data ({start_date.strftime('%Y-%m-%d')})")
    else:
        start_date = datetime(2026, 1, 1)
        end_date = datetime(2026, 7, 14)
        log.info(f"Historical mode: Fetching from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            log.info("Navigating to https://www.supplynote.in/signin ...")
            page.goto("https://www.supplynote.in/signin", wait_until="domcontentloaded", timeout=60000)
            
            log.info("Logging in...")
            page.fill('input[name="username"], input[name="email"], input[placeholder*="username" i], input[placeholder*="email" i]', SN_USERNAME)
            page.fill('input[type="password"]', SN_PASSWORD)
            page.click('button[type="submit"]')
            
            try:
                page.wait_for_url(lambda url: "/signin" not in url and "/login" not in url, timeout=20000)
                log.info("Logged in successfully!")
            except PWTimeout:
                log.error("Login failed (timeout waiting for redirect).")
                return

            curr_date = start_date
            while curr_date <= end_date:
                plan_date_utc = curr_date.strftime("%Y-%m-%dT18:30:00.000Z")
                log.info(f"Processing date: {curr_date.strftime('%Y-%m-%d')}")
                
                versions = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('/api/demandplan/history/semiFinished?business={BUSINESS_ID}&planDate={plan_date_utc}', {{
                            headers: {{ 'Accept': 'application/json' }}
                        }});
                        const body = await resp.json();
                        return body.data || [];
                    }} catch(e) {{ return []; }}
                }}""")
                
                if not versions:
                    log.warning(f"  No versions found for {curr_date.strftime('%Y-%m-%d')}.")
                    curr_date += timedelta(days=1)
                    continue
                
                version_key = versions[0].get("versionKey")
                if not version_key:
                    log.warning(f"  Version key not found in data for {curr_date.strftime('%Y-%m-%d')}.")
                    curr_date += timedelta(days=1)
                    continue
                
                # Check if file already exists before doing slow API call
                import glob
                existing = glob.glob(os.path.join(DROPZONE, f"CombinedIngredientsDemand_{version_key}_*.csv"))
                if existing:
                    log.info(f"  File for {version_key} already exists ({os.path.basename(existing[0])}). Skipping.")
                    curr_date += timedelta(days=1)
                    continue
                
                # Fetch the S3 URL with aggressive retries
                s3_url = None
                for attempt in range(5):
                    log.info(f"  Attempt {attempt+1}/5 to get S3 URL for version {version_key}...")
                    s3_url = page.evaluate(f"""async () => {{
                        try {{
                            const resp = await fetch('/api/demandplan/download/semiFinished-combined?type=all&versionKey={version_key}', {{
                                headers: {{ 'Accept': 'application/json' }}
                            }});
                            if (resp.status === 504) return '504';
                            if (!resp.ok) return 'error';
                            const body = await resp.json();
                            return body.data || null;
                        }} catch(e) {{ return 'error'; }}
                    }}""")
                    
                    if s3_url == '504':
                        log.warning(f"    504 Gateway Timeout inside browser. Waiting 30s...")
                        time.sleep(30)
                    elif s3_url == 'error' or not s3_url:
                        log.warning(f"    Failed to get URL inside browser.")
                        time.sleep(10)
                    else:
                        log.info(f"    Got S3 URL: {s3_url[:60]}...")
                        break
                
                if not s3_url or s3_url in ['504', 'error']:
                    log.error(f"  Failed to get S3 URL for {curr_date.strftime('%Y-%m-%d')} after 5 attempts.")
                    curr_date += timedelta(days=1)
                    continue
                
                filename = s3_url.split('/')[-1].split('?')[0]
                save_path = os.path.join(DROPZONE, filename)
                
                log.info(f"  Downloading CSV to {save_path}...")
                import requests
                r = requests.get(s3_url, stream=True)
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        if chunk: f.write(chunk)
                log.info(f"  Downloaded successfully.")
                
                curr_date += timedelta(days=1)
                time.sleep(2)  # brief pause before next day
                
        except Exception as e:
            log.error(f"Error during Playwright execution: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()

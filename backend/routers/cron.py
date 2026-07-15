import os
import sys
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
import logging

log = logging.getLogger(__name__)

# Add scripts directory to path so we can import the scripts directly
scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

try:
    from fetch_all_ingredients_playwright import run as run_download
    from process_supplynote_dropzone import run as run_process
except ImportError as e:
    log.error(f"Could not import scripts: {e}")

router = APIRouter()

# Read the secret token from the environment variable (or hardcode a fallback for testing)
CRON_SECRET_TOKEN = os.getenv("CRON_SECRET_TOKEN", "my_super_secret_cron_token_123")

def run_daily_sync_background():
    """Background task that runs the daily download and DB processing"""
    log.info("--- Starting Background Cron Sync ---")
    try:
        log.info("Step 1: Downloading Yesterday's Data...")
        run_download(yesterday_only=True)
        
        log.info("Step 2: Processing and Upserting to PostgreSQL...")
        run_process()
        
        log.info("--- Background Cron Sync Completed Successfully ---")
    except Exception as e:
        log.error(f"Background Cron Sync Failed: {e}")

@router.post("/sync-supplynote", summary="Daily SupplyNote Sync Endpoint for cron-job.org")
async def trigger_supplynote_sync(
    background_tasks: BackgroundTasks, 
    token: str = Query(..., description="Secret token to authorize the sync")
):
    """
    This endpoint is designed to be pinged by cron-job.org daily at 2:00 AM IST.
    It instantly returns a 200 OK so cron-job.org doesn't timeout,
    and runs the 60-second Playwright scraper + DB upload in the background.
    """
    if token != CRON_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid cron token")
    
    # Queue the heavy lifting in the background
    background_tasks.add_task(run_daily_sync_background)
    
    return {
        "status": "success", 
        "message": "Daily SupplyNote sync triggered successfully in the background."
    }

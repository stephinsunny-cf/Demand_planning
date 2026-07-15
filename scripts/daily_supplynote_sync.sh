#!/bin/bash

# ==============================================================================
# Daily SupplyNote Sync Script
# Scheduled via Cron to run daily at 2:00 AM IST
# ==============================================================================

# 1. Navigate to the absolute path of the project directory
# IMPORTANT: Change this to the actual absolute path where your repo lives on the server!
PROJECT_DIR="/path/to/your/demand-planning"
cd "$PROJECT_DIR" || exit 1

# 2. Activate the virtual environment if you have one
# source venv/bin/activate

# 3. Export environment variables if they aren't in a .env file (Optional)
# export SUPPLYNOTE_USER="your_user"
# export PG_HOST="103.172.150.31"
# etc...

echo "[$(date)] Starting Daily SupplyNote Sync..."

# 4. Run the Playwright script for yesterday's date only
echo "[$(date)] Step 1: Downloading Yesterday's Data..."
python3 scripts/fetch_all_ingredients_playwright.py --yesterday
if [ $? -ne 0 ]; then
    echo "[$(date)] ERROR: Playwright download failed!"
    exit 1
fi

# 5. Run the Database processing script
echo "[$(date)] Step 2: Processing and Uploading to PostgreSQL..."
python3 scripts/process_supplynote_dropzone.py
if [ $? -ne 0 ]; then
    echo "[$(date)] ERROR: Database processing failed!"
    exit 1
fi

echo "[$(date)] Daily Sync Complete!"

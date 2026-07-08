# run_nightly.py
# Runs every night to keep stock and sales data up to date.
# Scheduled via Windows Task Scheduler to run at 11:30 PM IST daily.

import subprocess
import sys
import os
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "logs", "nightly.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def run(script):
    log(f"Running: {script}")
    result = subprocess.run(
        [sys.executable, script],
        cwd=os.path.dirname(__file__),
        capture_output=True, text=True
    )
    if result.stdout:
        log(result.stdout.strip())
    if result.stderr:
        log(f"STDERR: {result.stderr.strip()}")
    if result.returncode != 0:
        log(f"ERROR: {script} failed with exit code {result.returncode}")
    else:
        log(f"OK: {script} completed successfully")

if __name__ == "__main__":
    log("=" * 60)
    log("NIGHTLY UPDATE STARTED")
    log("=" * 60)

    # 1. Refresh live stock from SupplyNote (all 368 outlets)
    run("pipeline/stock_extractor.py")

    # 2. Update today's sales data from UrbanPiper
    run("pipeline/daily_sales_updater.py")

    # 3. Refresh recipe master (BOMs + yield factors)
    run("pipeline/recipe_extractor.py")

    log("NIGHTLY UPDATE COMPLETE")
    log("=" * 60)

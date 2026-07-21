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
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(script):
    log(f"Running: {script}")
    result = subprocess.run(
        [sys.executable, script],
        cwd=os.path.dirname(__file__),
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
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

    # 1. Fetch live stock from SupplyNote API directly
    run("scripts/sync_supplynote_daily.py")

    # 2. Run the Full Demand Planning Pipeline (Sales, Forecast, Supply, Warehouse, Procurement, Alerts)
    run("pipeline/main.py")

    log("NIGHTLY UPDATE COMPLETE")
    log("=" * 60)

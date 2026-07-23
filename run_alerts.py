import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(r'd:\demand-planning\.env')
from pipeline.engines.alert_engine import run
alerts = run()
print(f"Generated {len(alerts)} new alerts.")

import asyncio
from backend.main import app
from backend.auth import UserContext
from fastapi.testclient import TestClient

async def run_audit():
    print("Extracting routes...")
    for route in app.routes:
        if hasattr(route, "endpoint"):
            print(route.path)

if __name__ == "__main__":
    asyncio.run(run_audit())

from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import get_current_user, UserContext

# Bypass auth
app.dependency_overrides[get_current_user] = lambda: UserContext(user_id="test", role="super_admin", email="test@test.com")

client = TestClient(app)

print("Starting endpoint audit...")
failed_endpoints = []
for route in app.routes:
    if hasattr(route, "endpoint") and route.path.startswith("/api/"):
        ep = route.path
        # Provide default query params to prevent 422 Unprocessable Entity
        url = ep
        if "/api/sales" in ep:
            url += "?start_date=2026-06-21&end_date=2026-07-21"
        try:
            response = client.get(url)
            print(f"{ep}: {response.status_code}")
            if response.status_code == 500:
                print(f"  -> ERROR: {response.text}")
                failed_endpoints.append(ep)
        except Exception as e:
            print(f"{ep}: CRASH -> {e}")
            failed_endpoints.append(ep)

if failed_endpoints:
    print(f"\nAUDIT FAILED! Found {len(failed_endpoints)} endpoints throwing 500s:")
    for ep in failed_endpoints:
        print(f"- {ep}")
else:
    print("\nAUDIT PASSED! All endpoints returned cleanly without 500s.")

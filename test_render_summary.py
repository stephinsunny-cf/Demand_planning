import requests

url = "https://demand-planning-8r9g.onrender.com/api/dashboard/summary"
headers = {
    "Origin": "https://demand-planning.vercel.app"
}

try:
    print("Testing GET request to /api/dashboard/summary...")
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

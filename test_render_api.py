import requests

url = "https://demand-planning-8r9g.onrender.com/api/dashboard/stats"
headers = {
    "Origin": "https://demand-planning.vercel.app"
}

try:
    print("Testing GET request...")
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {response.headers}")
    print(f"Response: {response.text[:200]}")
    
    print("\nTesting OPTIONS (Preflight) request...")
    options_resp = requests.options(url, headers={
        "Origin": "https://demand-planning.vercel.app",
        "Access-Control-Request-Method": "GET"
    })
    print(f"OPTIONS Status: {options_resp.status_code}")
    print(f"OPTIONS Headers: {options_resp.headers}")
    
except Exception as e:
    print(f"Error: {e}")

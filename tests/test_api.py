
import httpx
import json

BASE_URL = "http://localhost:25503/v3"
endpoint = "/option/list/expirations"
params = {'symbol': 'GOOG', 'format': 'json'}

try:
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        response = client.get(endpoint, params=params)
        response.raise_for_status()
        
        # Parse and print the JSON response
        data = response.json()
        print(json.dumps(data, indent=2))

except httpx.RequestError as e:
    print(f"An error occurred while requesting {e.request.url!r}.")
    print(f"Error: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

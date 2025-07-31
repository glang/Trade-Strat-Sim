

import httpx
import json

BASE_URL = "http://localhost:25503/v3"
ENDPOINT = "/option/history/eod"

# Parameters for a specific expiration on a specific date
PARAMS = {
    'symbol': 'GOOG',
    'expiration': '2024-01-19',
    'start_date': '2023-01-03',
    'end_date': '2023-01-03',
    'format': 'json'
}

print(f"▶️  Testing endpoint: {BASE_URL}{ENDPOINT}")
print(f"   Parameters: {PARAMS}")

try:
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        response = client.get(ENDPOINT, params=PARAMS)
        response.raise_for_status()
        
        data = response.json()
        
        print("\n✅ Request successful!")
        print(f"   Number of contracts returned: {len(data.get('contract', []))}")
        
        # Print the first 3 contracts to inspect the structure
        if data.get('contract'):
            print("\n🔍 Sample of first 3 contracts:")
            
            # The new API returns data in a columnar format, so we need to reconstruct the first few rows.
            contracts = data.get('contract', [])
            strikes = data.get('strike', [])
            rights = data.get('right', [])
            closes = data.get('close', [])
            
            for i in range(min(3, len(contracts))):
                record = {
                    "contract": contracts[i],
                    "strike": strikes[i],
                    "right": rights[i],
                    "close": closes[i]
                }
                print(json.dumps(record, indent=2))

except httpx.HTTPStatusError as e:
    print(f"\n❌ HTTP Error: {e.response.status_code} - {e.response.text}")
except httpx.RequestError as e:
    print(f"\n❌ Request Error: An error occurred while requesting {e.request.url!r}.")
    print(f"   Details: {e}")
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")



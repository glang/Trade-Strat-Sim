import httpx
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

# --- Constants ---
BASE_URL = "http://localhost:25503/v3"

# --- Functions to be tested ---

def get_bulk_eod_data_httpx(symbol: str, exp_date: str, trade_date: str, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """Fetches bulk EOD data using the httpx library."""
    ENDPOINT = "/option/history/eod"
    
    try:
        exp_formatted = datetime.strptime(exp_date, '%Y%m%d').strftime('%Y-%m-%d')
    except ValueError:
        exp_formatted = exp_date

    params = {
        'symbol': symbol,
        'expiration': exp_formatted,
        'start_date': trade_date,
        'end_date': trade_date,
        'strike': '*',
        'format': 'json'
    }
    
    if not quiet:
        print(f"⚡ Calling API: {BASE_URL}{ENDPOINT}")
        print(f"   Params: {params}")

    try:
        response = httpx.get(f"{BASE_URL}{ENDPOINT}", params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get('strike'):
             if not quiet: print(f"✅ Bulk EOD returned {len(data['strike'])} records")
             return data
        if not quiet: print("⚠️  API returned success but no contract data found.")
        return None

    except httpx.HTTPStatusError as e:
        if not quiet: print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        if not quiet: print(f"❌ An unexpected error occurred: {e}")
        return None

def filter_itm_calls_from_bulk(bulk_data: Dict[str, Any], stock_price: float, quiet: bool = False) -> List[Dict[str, Any]]:
    if not bulk_data or 'strike' not in bulk_data:
        return []
    
    valid_calls = []
    stock_price_millidollars = stock_price * 1000
    
    num_contracts = len(bulk_data['strike'])
    strikes = bulk_data.get('strike', [0.0] * num_contracts)
    rights = bulk_data.get('right', [''] * num_contracts)
    closes = bulk_data.get('close', [0.0] * num_contracts)
    bids = bulk_data.get('bid', [0.0] * num_contracts)
    asks = bulk_data.get('ask', [0.0] * num_contracts)

    for i in range(num_contracts):
        try:
            strike_dollars = strikes[i]
            strike_millidollars = int(strike_dollars * 1000)
            right = rights[i]
            close_price = closes[i] if closes[i] else 0
            bid = bids[i] if bids[i] else 0
            ask = asks[i] if asks[i] else 0

            if right.upper() != 'CALL': continue
            if strike_millidollars < stock_price_millidollars:
                if close_price > 0 or (bid > 0 and ask > 0):
                    distance = abs(strike_millidollars - stock_price_millidollars)
                    valid_calls.append({
                        'strike': strike_dollars,
                        'distance': distance / 1000.0,  # Convert distance to dollars for display
                        'close': close_price, 
                        'bid': bid, 
                        'ask': ask, 
                        'data_quality': 'excellent' if close_price > 0 else 'good'
                    })
        except (ValueError, IndexError, TypeError):
            continue
    
    # Sort by the raw distance, not the display value
    valid_calls.sort(key=lambda x: x['distance'])
    if not quiet: print(f"✅ Found {len(valid_calls)} valid ITM calls")
    return valid_calls

# --- Test Execution ---

def main():
    print("▶️  Testing get_bulk_eod_data and filter_itm_calls_from_bulk using httpx")
    
    symbol = "GOOG"
    exp_date = "20250117"
    trade_date = "20231229"
    stock_price = 140.93 # GOOG price on 2023-12-29
    
    print(f"   Fetching data for {symbol} on {trade_date} for expiration {exp_date}")

    bulk_data = get_bulk_eod_data_httpx(symbol, exp_date, trade_date)
    
    if not bulk_data:
        print("\n❌ Test Failed: Could not retrieve bulk EOD data.")
        return

    print(f"\n   Filtering ITM calls with stock price ${stock_price:.2f}...")
    itm_calls = filter_itm_calls_from_bulk(bulk_data, stock_price)
    
    if not itm_calls:
        print("\n❌ Test Failed: No ITM calls were found after filtering.")
        return
        
    print("\n✅ Test Successful!")
    print(f"   Total ITM calls found: {len(itm_calls)}")
    print("\n🔍 Sample of first 5 filtered ITM calls (closest to the money):")
    for call in itm_calls[:5]:
        print(json.dumps(call, indent=2))

if __name__ == "__main__":
    main()
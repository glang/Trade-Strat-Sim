#!/usr/bin/env python3
"""
Smart LEAPS Backtest with Enhanced Caching & Error Handling
- Intelligent cache management (permanent vs temporary data)
- Smart error classification (API failures vs market closed)
- Multi-provider fallback (Tiingo → MarketStack)
- Zero API calls for repeated analysis
"""

import subprocess
import json
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Cache file location
CACHE_FILE = "smart_stock_cache.json"

# Error classification constants
PERMANENT_ERRORS = ["market_closed", "no_data_available"]
TEMPORARY_ERRORS = ["rate_limit", "timeout", "server_error", "unauthorized", "network_error"]
CACHE_FOREVER_TYPES = ["success", "market_closed", "first_market_day"]

def load_smart_cache() -> Dict[str, Any]:
    """Load smart cache with metadata tracking"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                print(f"📦 Loaded cache: {get_cache_stats(cache)}")
                return cache
    except Exception as e:
        print(f"⚠️  Cache load error: {e}")
    
    return {
        "providers": {"tiingo": {}, "marketstack": {}},
        "meta": {"created": str(datetime.now()), "stats": {}},
        "market_days": {}
    }

def save_smart_cache(cache_data: Dict[str, Any]) -> None:
    """Save cache with updated statistics"""
    try:
        cache_data["meta"]["updated"] = str(datetime.now())
        cache_data["meta"]["stats"] = calculate_cache_stats(cache_data)
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        print(f"💾 Cache saved: {get_cache_stats(cache_data)}")
    except Exception as e:
        print(f"⚠️  Cache save error: {e}")

def calculate_cache_stats(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate comprehensive cache statistics"""
    stats = {"total_entries": 0, "by_provider": {}, "by_type": {}}
    
    for provider, entries in cache.get("providers", {}).items():
        provider_stats = {
            "total": len(entries),
            "success": 0,
            "market_closed": 0,
            "api_failures": 0
        }
        
        for entry in entries.values():
            if entry.get("success"):
                provider_stats["success"] += 1
            elif entry.get("error") == "market_closed":
                provider_stats["market_closed"] += 1
            elif entry.get("error") in TEMPORARY_ERRORS:
                provider_stats["api_failures"] += 1
        
        stats["by_provider"][provider] = provider_stats
        stats["total_entries"] += provider_stats["total"]
    
    stats["market_days_cached"] = len(cache.get("market_days", {}))
    return stats

def get_cache_stats(cache: Dict[str, Any]) -> str:
    """Get human-readable cache statistics"""
    stats = cache.get("meta", {}).get("stats", {})
    if not stats:
        return "empty cache"
    
    total = stats.get("total_entries", 0)
    market_days = stats.get("market_days_cached", 0)
    return f"{total} entries, {market_days} market days"

def is_cache_entry_valid(entry: Dict[str, Any]) -> bool:
    """Determine if cache entry is still valid"""
    if not entry.get("cached_at"):
        return False
    
    # Permanent data never expires
    if entry.get("cache_type") in CACHE_FOREVER_TYPES:
        return True
    
    # Temporary failures expire after 1 hour
    cached_time = datetime.fromisoformat(entry["cached_at"])
    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
    return age_hours < 1.0

def api_call_with_classification(cmd: str) -> Dict[str, Any]:
    """Make API call with smart error classification"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout:
            try:
                return {"raw_response": json.loads(result.stdout), "call_success": True}
            except json.JSONDecodeError:
                return {"error": "json_decode", "message": "Invalid JSON response", "call_success": False}
        else:
            return {"error": "http_error", "message": f"HTTP {result.returncode}", "call_success": False}
            
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "message": "Request timed out", "call_success": False}
    except Exception as e:
        return {"error": "network_error", "message": str(e), "call_success": False}

def get_api_keys() -> Dict[str, str]:
    """Get all API keys from environment"""
    keys = {}
    try:
        env_path = os.path.join(os.path.expanduser('~/trade-strat-sim'), '.env')
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('TIINGO_API_KEY='):
                    keys['tiingo'] = line.split('=', 1)[1].strip()
                elif line.startswith('MARKETSTACK_API_KEY='):
                    keys['marketstack'] = line.split('=', 1)[1].strip()
    except Exception as e:
        print(f"⚠️  Error reading API keys: {e}")
    return keys

def classify_tiingo_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Classify Tiingo API response with smart error handling"""
    if not response.get("call_success"):
        # Network/timeout error
        return {
            "error": response.get("error", "unknown"),
            "message": response.get("message", "API call failed"),
            "provider": "tiingo",
            "cache_type": "temporary_failure"
        }
    
    raw = response.get("raw_response")
    
    if isinstance(raw, list):
        if len(raw) > 0 and "open" in raw[0]:
            # Success - valid stock data
            return {
                "success": True,
                "price": raw[0]["open"],
                "date": raw[0].get("date"),
                "provider": "tiingo",
                "cache_type": "success",
                "full_data": raw[0]
            }
        else:
            # Empty array = market closed
            return {
                "error": "market_closed",
                "message": "No trading data for this date",
                "provider": "tiingo",
                "cache_type": "market_closed"
            }
    elif isinstance(raw, dict) and "error" in raw:
        # API returned an error object
        error_msg = raw.get("error", {}).get("message", "Unknown API error")
        if "rate limit" in error_msg.lower():
            error_type = "rate_limit"
        elif "unauthorized" in error_msg.lower():
            error_type = "unauthorized"
        else:
            error_type = "server_error"
            
        return {
            "error": error_type,
            "message": error_msg,
            "provider": "tiingo",
            "cache_type": "temporary_failure"
        }
    else:
        # Unexpected format
        return {
            "error": "unexpected_format",
            "message": f"Unexpected response format: {type(raw)}",
            "provider": "tiingo",
            "cache_type": "temporary_failure"
        }

def classify_marketstack_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Classify MarketStack API response with smart error handling"""
    if not response.get("call_success"):
        return {
            "error": response.get("error", "unknown"),
            "message": response.get("message", "API call failed"),
            "provider": "marketstack",
            "cache_type": "temporary_failure"
        }
    
    raw = response.get("raw_response")
    
    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw["data"], list):
            if len(raw["data"]) > 0 and "open" in raw["data"][0]:
                # Success
                return {
                    "success": True,
                    "price": raw["data"][0]["open"],
                    "date": raw["data"][0].get("date"),
                    "provider": "marketstack",
                    "cache_type": "success",
                    "full_data": raw["data"][0]
                }
            else:
                # Empty data = market closed
                return {
                    "error": "market_closed",
                    "message": "No trading data for this date",
                    "provider": "marketstack",
                    "cache_type": "market_closed"
                }
        elif "error" in raw:
            # MarketStack error format
            error_info = raw["error"]
            error_code = error_info.get("code", "unknown")
            
            if "rate" in error_code.lower() or "limit" in error_code.lower():
                error_type = "rate_limit"
            elif "access" in error_code.lower() or "auth" in error_code.lower():
                error_type = "unauthorized"
            else:
                error_type = "server_error"
                
            return {
                "error": error_type,
                "message": error_info.get("message", "MarketStack API error"),
                "provider": "marketstack",
                "cache_type": "temporary_failure"
            }
    
    return {
        "error": "unexpected_format",
        "message": f"Unexpected MarketStack response: {type(raw)}",
        "provider": "marketstack",
        "cache_type": "temporary_failure"
    }

def get_stock_price_tiingo(symbol: str, date: str) -> Dict[str, Any]:
    """Get stock price from Tiingo with smart classification"""
    formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    api_keys = get_api_keys()
    
    if 'tiingo' not in api_keys:
        return {
            "error": "no_api_key",
            "message": "Tiingo API key not configured",
            "provider": "tiingo",
            "cache_type": "temporary_failure"
        }
    
    cmd = f'curl -s "https://api.tiingo.com/tiingo/daily/{symbol}/prices?startDate={formatted_date}&endDate={formatted_date}&token={api_keys["tiingo"]}"'
    response = api_call_with_classification(cmd)
    return classify_tiingo_response(response)

def get_stock_price_marketstack(symbol: str, date: str) -> Dict[str, Any]:
    """Get stock price from MarketStack with smart classification"""
    formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    api_keys = get_api_keys()
    
    if 'marketstack' not in api_keys:
        return {
            "error": "no_api_key", 
            "message": "MarketStack API key not configured",
            "provider": "marketstack",
            "cache_type": "temporary_failure"
        }
    
    cmd = f'curl -s "http://api.marketstack.com/v1/eod?access_key={api_keys["marketstack"]}&symbols={symbol}&date_from={formatted_date}&date_to={formatted_date}"'
    response = api_call_with_classification(cmd)
    return classify_marketstack_response(response)

def get_cached_result(cache: Dict[str, Any], provider: str, symbol: str, date: str) -> Optional[Dict[str, Any]]:
    """Get cached result if valid"""
    cache_key = f"{provider}_{symbol}_{date}"
    cached_entry = cache.get("providers", {}).get(provider, {}).get(cache_key)
    
    if cached_entry and is_cache_entry_valid(cached_entry):
        print(f"📦 Cache hit: {symbol} {date} from {provider} ({cached_entry.get('cache_type')})")
        return cached_entry
    elif cached_entry:
        print(f"🗑️  Cache expired: {symbol} {date} from {provider}")
        # Remove expired entry
        del cache["providers"][provider][cache_key]
    
    return None

def cache_result(cache: Dict[str, Any], provider: str, symbol: str, date: str, result: Dict[str, Any]) -> None:
    """Cache result with intelligent caching rules"""
    cache_key = f"{provider}_{symbol}_{date}"
    cache_type = result.get("cache_type", "unknown")
    
    # Only cache permanent data and avoid caching temporary failures
    if cache_type in CACHE_FOREVER_TYPES or cache_type == "temporary_failure":
        if provider not in cache["providers"]:
            cache["providers"][provider] = {}
        
        # Add caching metadata
        result["cached_at"] = str(datetime.now())
        cache["providers"][provider][cache_key] = result
        
        if cache_type in CACHE_FOREVER_TYPES:
            print(f"💾 Cached permanently: {symbol} {date} ({cache_type})")
        else:
            print(f"⏳ Cached temporarily: {symbol} {date} ({cache_type})")
    else:
        print(f"🚫 Not cached: {symbol} {date} ({cache_type})")

def get_stock_price_with_smart_fallback(symbol: str, date: str) -> Optional[float]:
    """Get stock price with intelligent provider fallback and caching"""
    print(f"💰 Getting stock price: {symbol} {date}")
    cache = load_smart_cache()
    
    # Try Tiingo first (check cache)
    cached_result = get_cached_result(cache, "tiingo", symbol, date)
    if cached_result:
        if cached_result.get("success"):
            return cached_result["price"]
        elif cached_result.get("error") == "market_closed":
            return None
        # If cached failure, fall through to try fresh call
    
    # Make fresh Tiingo call
    tiingo_result = get_stock_price_tiingo(symbol, date)
    cache_result(cache, "tiingo", symbol, date, tiingo_result)
    
    if tiingo_result.get("success"):
        save_smart_cache(cache)
        print(f"✅ Tiingo: ${tiingo_result['price']:.2f}")
        return tiingo_result["price"]
    elif tiingo_result.get("error") == "market_closed":
        save_smart_cache(cache)
        print(f"🏁 Market closed: {date}")
        return None
    else:
        # API failure - try MarketStack fallback
        print(f"⚠️  Tiingo failed: {tiingo_result.get('error')} - trying MarketStack...")
        
        # Check MarketStack cache
        cached_ms_result = get_cached_result(cache, "marketstack", symbol, date)
        if cached_ms_result:
            if cached_ms_result.get("success"):
                return cached_ms_result["price"]
            elif cached_ms_result.get("error") == "market_closed":
                return None
        
        # Fresh MarketStack call
        ms_result = get_stock_price_marketstack(symbol, date)
        cache_result(cache, "marketstack", symbol, date, ms_result)
        save_smart_cache(cache)
        
        if ms_result.get("success"):
            print(f"✅ MarketStack fallback: ${ms_result['price']:.2f}")
            return ms_result["price"]
        elif ms_result.get("error") == "market_closed":
            print(f"🏁 Market closed confirmed by MarketStack: {date}")
            return None
        else:
            print(f"❌ Both providers failed: Tiingo({tiingo_result.get('error')}) MarketStack({ms_result.get('error')})")
            return None

def find_first_market_day_smart(year: int, symbol: str = "GOOG") -> Optional[str]:
    """Find first market day with smart caching"""
    print(f"🗓️  Finding first market day of {year}...")
    cache = load_smart_cache()
    
    # Check cache for known first market day
    cache_key = f"first_market_day_{year}_{symbol}"
    if cache_key in cache.get("market_days", {}):
        cached_date = cache["market_days"][cache_key]
        print(f"📦 Cached first market day: {cached_date}")
        return cached_date
    
    # Search for first market day
    current_date = datetime(year, 1, 1)
    
    for days_offset in range(15):  # Extended range for holiday clusters
        test_date = current_date + timedelta(days=days_offset)
        
        # Skip weekends
        if test_date.weekday() > 4:
            continue
        
        date_str = test_date.strftime('%Y%m%d')
        stock_price = get_stock_price_with_smart_fallback(symbol, date_str)
        
        if stock_price and stock_price > 0:
            # Cache the first market day permanently
            if "market_days" not in cache:
                cache["market_days"] = {}
            cache["market_days"][cache_key] = date_str
            save_smart_cache(cache)
            
            print(f"✅ First market day: {date_str} ({test_date.strftime('%A')}) - ${stock_price:.2f}")
            return date_str
        else:
            print(f"❌ Market closed: {date_str} ({test_date.strftime('%A')})")
    
    print(f"❌ Could not find first market day for {year}")
    return None

def get_last_trading_day_smart(year: int, symbol: str = "GOOG") -> Optional[str]:
    """Find last trading day with smart caching"""
    if year == 2025:
        return "20250702"  # Current partial year
    
    cache = load_smart_cache()
    cache_key = f"last_market_day_{year}_{symbol}"
    
    if cache_key in cache.get("market_days", {}):
        cached_date = cache["market_days"][cache_key]
        print(f"📦 Cached last market day: {cached_date}")
        return cached_date
    
    current_date = datetime(year, 12, 31)
    
    for days_offset in range(10):
        test_date = current_date - timedelta(days=days_offset)
        
        if test_date.weekday() > 4:
            continue
        
        date_str = test_date.strftime('%Y%m%d')
        stock_price = get_stock_price_with_smart_fallback(symbol, date_str)
        
        if stock_price and stock_price > 0:
            # Cache the result
            if "market_days" not in cache:
                cache["market_days"] = {}
            cache["market_days"][cache_key] = date_str
            save_smart_cache(cache)
            return date_str
    
    return None

def analyze_smart_cache():
    """Analyze smart cache performance and statistics"""
    cache = load_smart_cache()
    stats = cache.get("meta", {}).get("stats", {})
    
    print("\n📊 SMART CACHE ANALYSIS")
    print("=" * 60)
    
    if not stats:
        print("No cache statistics available")
        return
    
    print(f"Total Entries: {stats.get('total_entries', 0)}")
    print(f"Market Days Cached: {stats.get('market_days_cached', 0)}")
    
    for provider, provider_stats in stats.get("by_provider", {}).items():
        print(f"\n{provider.upper()} Provider:")
        print(f"  Total: {provider_stats.get('total', 0)}")
        print(f"  Successful: {provider_stats.get('success', 0)}")
        print(f"  Market Closed: {provider_stats.get('market_closed', 0)}")
        print(f"  API Failures: {provider_stats.get('api_failures', 0)}")
    
    # Calculate efficiency
    total_entries = stats.get('total_entries', 0)
    if total_entries > 0:
        success_rate = sum(p.get('success', 0) for p in stats.get('by_provider', {}).values())
        efficiency = (success_rate / total_entries) * 100
        print(f"\nCache Efficiency: {efficiency:.1f}% successful lookups")
    
    # Show cache file info
    if os.path.exists(CACHE_FILE):
        file_size = os.path.getsize(CACHE_FILE)
        print(f"Cache File Size: {file_size:,} bytes")

def test_smart_system():
    """Test the smart caching and error handling system"""
    print("🚀 SMART LEAPS SYSTEM TEST")
    print("=" * 60)
    
    # Test 1: Known trading day
    print("\n1. Testing known trading day (2018-01-02):")
    price = get_stock_price_with_smart_fallback("GOOG", "20180102")
    print(f"Result: ${price:.2f}" if price else "No price available")
    
    # Test 2: Known holiday 
    print("\n2. Testing New Year's Day (2018-01-01):")
    price = get_stock_price_with_smart_fallback("GOOG", "20180101")
    print(f"Result: ${price:.2f}" if price else "Market closed (as expected)")
    
    # Test 3: First market day detection
    print("\n3. Testing first market day detection:")
    first_day = find_first_market_day_smart(2018)
    print(f"First market day 2018: {first_day}")
    
    # Test 4: Cache analysis
    print("\n4. Cache performance analysis:")
    analyze_smart_cache()
    
    # Test 5: Repeated call (should be cached)
    print("\n5. Testing cache hit (repeat call):")
    price = get_stock_price_with_smart_fallback("GOOG", "20180102")
    print(f"Result: ${price:.2f}" if price else "No price available")

if __name__ == "__main__":
    test_smart_system()
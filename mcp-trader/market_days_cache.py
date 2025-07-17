#!/usr/bin/env python3
"""
Market Days Cache System using ThetaData Trade Endpoint
Uses the list/dates/stock/trade endpoint to get actual trading days for accurate market day detection.
Caches results permanently since historical trading days never change.
"""

import subprocess
import json
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Cache file for market days
MARKET_DAYS_CACHE_FILE = "market_days_cache.json"

def api_call(cmd: str, quiet: bool = False) -> dict:
    """Make ThetaData API call"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout and not result.stdout.startswith(':'):
            return json.loads(result.stdout)
    except Exception as e:
        if not quiet: print(f"⚠️  ThetaData API error: {str(e)}")
    return {}

def load_market_days_cache(quiet: bool = False) -> Dict[str, Any]:
    """Load market days cache"""
    try:
        if os.path.exists(MARKET_DAYS_CACHE_FILE):
            with open(MARKET_DAYS_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                if not quiet:
                    total_days = len(cache.get('trading_days', {}))
                    years = len(cache.get('years', {}))
                    print(f"📦 Loaded market days cache: {total_days} trading days, {years} years cached")
                return cache
    except Exception as e:
        if not quiet: print(f"⚠️  Market days cache load error: {e}")
    
    return {
        "trading_days": {},
        "years": {},
        "symbols": {},
        "meta": {
            "created": str(datetime.now()),
            "cache_version": "1.0",
            "data_source": "ThetaData list/dates/stock/trade"
        }
    }

def save_market_days_cache(cache_data: Dict[str, Any], quiet: bool = False) -> None:
    """Save market days cache"""
    try:
        cache_data["meta"]["updated"] = str(datetime.now())
        with open(MARKET_DAYS_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        if not quiet:
            total_days = len(cache_data.get('trading_days', {}))
            years = len(cache_data.get('years', {}))
            print(f"💾 Market days cache saved: {total_days} trading days, {years} years")
    except Exception as e:
        if not quiet: print(f"⚠️  Market days cache save error: {e}")

def get_trading_days_for_year(symbol: str, year: int, quiet: bool = False) -> Optional[List[str]]:
    """
    Get all trading days for a specific year using ThetaData list/dates/stock/trade endpoint
    """
    cache = load_market_days_cache(quiet=quiet)
    cache_key = f"{symbol}_{year}"
    
    if cache_key in cache.get('symbols', {}):
        year_data = cache['years'].get(str(year), {})
        if year_data.get('trading_days'):
            if not quiet: print(f"📦 Cache hit: {symbol} {year} trading days ({len(year_data['trading_days'])} days)")
            return year_data['trading_days']
    
    if not quiet: print(f"🔍 Fetching trading days for {symbol} {year} using ThetaData list/dates endpoint...")
    
    cmd = f'curl -s "http://127.0.0.1:25510/v2/list/dates/stock/trade?root={symbol}&use_csv=true"'
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not result.stdout:
            if not quiet: print(f"❌ No response from ThetaData for {symbol}")
            return None
        
        trading_days = []
        lines = result.stdout.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.lower().startswith('date'):
                continue
            try:
                if line.isdigit() and len(line) == 8:
                    datetime.strptime(line, '%Y%m%d')
                    trading_days.append(line)
                elif '-' in line or '/' in line:
                    clean_date = line.replace('-', '').replace('/', '').replace(' ', '')
                    if clean_date.isdigit() and len(clean_date) == 8:
                        datetime.strptime(clean_date, '%Y%m%d')
                        trading_days.append(clean_date)
            except (ValueError, TypeError):
                continue
        
        if not trading_days:
            if not quiet: print(f"❌ No valid trading days found in response for {symbol}")
            return None
        
        trading_days = sorted(list(set(trading_days)))
        year_str = str(year)
        year_trading_days = [d for d in trading_days if d.startswith(year_str)]
        
        if not year_trading_days:
            if not quiet: print(f"❌ No trading days found for {symbol} {year}")
            return None
        
        if not quiet:
            print(f"✅ Found {len(year_trading_days)} trading days for {symbol} {year}")
            print(f"   First: {year_trading_days[0]} Last: {year_trading_days[-1]}")
        
        if 'symbols' not in cache: cache['symbols'] = {}
        if 'years' not in cache: cache['years'] = {}
        if 'trading_days' not in cache: cache['trading_days'] = {}
        
        for day in year_trading_days:
            cache['trading_days'][day] = {'symbol': symbol, 'year': year, 'cached_at': str(datetime.now())}
        
        cache['years'][str(year)] = {'symbol': symbol, 'first_trading_day': year_trading_days[0], 'last_trading_day': year_trading_days[-1], 'total_trading_days': len(year_trading_days), 'trading_days': year_trading_days, 'cached_at': str(datetime.now())}
        
        if symbol not in cache['symbols']: cache['symbols'][symbol] = []
        if year not in cache['symbols'][symbol]:
            cache['symbols'][symbol].append(year)
            cache['symbols'][symbol].sort()
        
        save_market_days_cache(cache, quiet=quiet)
        
        return year_trading_days
        
    except Exception as e:
        if not quiet: print(f"❌ Error fetching trading days for {symbol} {year}: {str(e)}")
        return None

def get_first_trading_day_of_year(symbol: str, year: int, quiet: bool = False) -> Optional[str]:
    cache = load_market_days_cache(quiet=quiet)
    year_data = cache.get('years', {}).get(str(year), {})
    if year_data.get('first_trading_day'):
        first_day = year_data['first_trading_day']
        if not quiet: print(f"📦 Cached first trading day: {symbol} {year} = {first_day}")
        return first_day
    trading_days = get_trading_days_for_year(symbol, year, quiet=quiet)
    if trading_days:
        first_day = trading_days[0]
        if not quiet: print(f"✅ First trading day: {symbol} {year} = {first_day}")
        return first_day
    return None

def get_last_trading_day_of_year(symbol: str, year: int, quiet: bool = False) -> Optional[str]:
    cache = load_market_days_cache(quiet=quiet)
    year_data = cache.get('years', {}).get(str(year), {})
    if year_data.get('last_trading_day'):
        last_day = year_data['last_trading_day']
        if not quiet: print(f"📦 Cached last trading day: {symbol} {year} = {last_day}")
        return last_day
    trading_days = get_trading_days_for_year(symbol, year, quiet=quiet)
    if trading_days:
        last_day = trading_days[-1]
        if not quiet: print(f"✅ Last trading day: {symbol} {year} = {last_day}")
        return last_day
    return None

def is_trading_day(symbol: str, date: str, quiet: bool = False) -> bool:
    try:
        date_dt = datetime.strptime(date, '%Y%m%d')
        year = date_dt.year
    except ValueError:
        return False
    cache = load_market_days_cache(quiet=quiet)
    if date in cache.get('trading_days', {}):
        return True
    year_data = cache.get('years', {}).get(str(year), {})
    if year_data.get('trading_days'):
        return date in year_data['trading_days']
    trading_days = get_trading_days_for_year(symbol, year, quiet=quiet)
    if trading_days:
        return date in trading_days
    return False

def get_trading_days_range(symbol: str, start_year: int, end_year: int, quiet: bool = False) -> Dict[int, Dict[str, str]]:
    result = {}
    for year in range(start_year, end_year + 1):
        first_day = get_first_trading_day_of_year(symbol, year, quiet=quiet)
        last_day = get_last_trading_day_of_year(symbol, year, quiet=quiet)
        if first_day and last_day:
            result[year] = {'first': first_day, 'last': last_day}
        else:
            if not quiet: print(f"⚠️  Could not get trading days for {symbol} {year}")
    return result

def get_most_recent_trading_day(symbol: str, quiet: bool = False) -> Optional[str]:
    current_year = datetime.now().year
    trading_days = get_trading_days_for_year(symbol, current_year, quiet=quiet)
    if not trading_days:
        if not quiet: print(f"❌ No trading days found for {symbol} {current_year}")
        return None
    today = datetime.now().strftime('%Y%m%d')
    available_days = [day for day in trading_days if day <= today]
    if not available_days:
        if not quiet: print(f"❌ No trading days available up to today for {symbol}")
        return None
    most_recent = max(available_days)
    if not quiet: print(f"📅 Most recent trading day: {symbol} {most_recent}")
    return most_recent

def get_first_trading_day_of_quarter(symbol: str, year: int, quarter: int, quiet: bool = False) -> Optional[str]:
    trading_days = get_trading_days_for_year(symbol, year, quiet=quiet)
    if not trading_days: return None
    month = (quarter - 1) * 3 + 1
    for day in trading_days:
        day_dt = datetime.strptime(day, '%Y%m%d')
        if day_dt.month >= month:
            return day
    return None

def get_last_trading_day_of_quarter(symbol: str, year: int, quarter: int, quiet: bool = False) -> Optional[str]:
    trading_days = get_trading_days_for_year(symbol, year, quiet=quiet)
    if not trading_days: return None
    month = quarter * 3
    last_day = None
    for day in trading_days:
        day_dt = datetime.strptime(day, '%Y%m%d')
        if day_dt.month <= month:
            last_day = day
        if day_dt.month > month:
            break
    return last_day

def analyze_market_days_cache(quiet: bool = False) -> None:
    cache = load_market_days_cache(quiet=quiet)
    if not quiet:
        print("📊 MARKET DAYS CACHE ANALYSIS")
        print("=" * 50)
        total_days = len(cache.get('trading_days', {}))
        total_years = len(cache.get('years', {}))
        total_symbols = len(cache.get('symbols', {}))
        print(f"Total trading days cached: {total_days}")
        print(f"Total years covered: {total_years}")
        print(f"Total symbols covered: {total_symbols}")
        print()
        for symbol, years in cache.get('symbols', {}).items():
            print(f"{symbol}: {len(years)} years ({min(years)}-{max(years)})")
        print()
        years_data = cache.get('years', {})
        if years_data:
            print("Year-by-year breakdown:")
            for year in sorted(years_data.keys()):
                year_info = years_data[year]
                first = year_info.get('first_trading_day', 'N/A')
                last = year_info.get('last_trading_day', 'N/A')
                total = year_info.get('total_trading_days', 0)
                print(f"  {year}: {first} → {last} ({total} days)")

def main():
    print("🎯 MARKET DAYS CACHE SYSTEM TEST")
    print("=" * 80)
    symbol = "GOOG"
    start_year = 2016
    end_year = 2025
    print(f"\n🔍 Getting trading days for {symbol} ({start_year}-{end_year})...")
    trading_days_by_year = get_trading_days_range(symbol, start_year, end_year)
    print(f"\n📊 RESULTS:")
    print("-" * 60)
    for year in range(start_year, end_year + 1):
        if year in trading_days_by_year:
            data = trading_days_by_year[year]
            first = data['first']
            last = data['last']
            cache = load_market_days_cache()
            year_data = cache.get('years', {}).get(str(year), {})
            trading_days_count = year_data.get('total_trading_days', 0)
            print(f"{year}: {first} → {last} ({trading_days_count} trading days)")
        else:
            print(f"{year}: ❌ No data available")
    print()
    analyze_market_days_cache()

if __name__ == "__main__":
    main()

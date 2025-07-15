#!/usr/bin/env python3
"""
Quarterly Rolling LEAPS Backtester

This script backtests two LEAPS (Long-term Equity AnticiPation Securities) strategies:

1.  **Annual January LEAPS**: Buys a LEAP expiring in the next January on the first
    trading day of the year and holds it until the last trading day of the year.
    This serves as a baseline for comparison.

2.  **Quarterly Rolling 15-Month LEAPS**: A more advanced strategy that aims to
    maintain a consistent time to expiration. It works as follows:
    - On the first trading day of Q1, it buys a LEAP with the expiration date
      closest to 15 months out.
    - At the end of each quarter, it "rolls" the position by selling the
      existing LEAP and buying a new one that is again ~15 months from expiration.
    - This ensures the time premium decay (theta) is managed more effectively.

The script uses the ThetaData API to fetch historically accurate option and stock
price data. It is optimized for speed by using bulk API calls where possible
while maintaining the accuracy of the backtest.
"""

import subprocess
import json
import time
import os
import requests
import argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Tuple, Optional, Any

# Import smart caching functions
from smart_leaps_backtest import (
    get_stock_price_with_smart_fallback,
    analyze_smart_cache
)

# Import ThetaData market days cache system
from market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_most_recent_trading_day,
    get_first_trading_day_of_quarter,
    get_last_trading_day_of_quarter
)

# --- Constants ---
THETADATA_API_BASE = "http://127.0.0.1:25510"
ENTRY_TIME_MS = 36000000  # 10:00 AM EST for precise entry price

def get_expirations_available_on_date(symbol: str, date_str: str) -> List[datetime.date]:
    """
    Gets a list of all unique expiration dates available for a symbol on a specific historical date.
    This function queries the v2/list/contracts/option/quote endpoint.

    Args:
        symbol: The root symbol (e.g., 'SPY', 'GOOG').
        date_str: The historical date in YYYYMMDD format for which to retrieve available contracts.

    Returns:
        A sorted list of unique datetime.date objects representing available expiration dates.
        Returns an empty list if no data is found or an error occurs.
    """
    print(f"🔍 Getting available expirations for {symbol} on {date_str}")
    
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/list/contracts/option/quote?root={symbol}&start_date={date_str}"'
    data = api_call(cmd)
    
    if not data or 'response' not in data:
        print(f"❌ No data returned for {symbol} on {date_str}")
        return []
    
    # Extract unique expiration dates
    expiration_set = set()
    
    for contract in data['response']:
        try:
            # Contract format: ["root", "expiration", "strike", "right"]
            if len(contract) >= 2:
                exp_str = str(contract[1])  # Expiration is at index 1
                if len(exp_str) == 8 and exp_str.isdigit():
                    exp_date = datetime.strptime(exp_str, '%Y%m%d').date()
                    expiration_set.add(exp_date)
        except (ValueError, IndexError, TypeError):
            continue
    
    # Convert to sorted list
    expirations = sorted(list(expiration_set))
    print(f"✅ Found {len(expirations)} unique expiration dates")
    
    return expirations

def find_closest_expiration_date(available_expirations: List[datetime.date], target_date: datetime.date) -> Optional[datetime.date]:
    """
    Find the expiration date closest to the target date.
    
    Args:
        available_expirations: List of available expiration dates
        target_date: Target expiration date (15 months from entry)
        
    Returns:
        The closest available expiration date, or None if no expirations available
    """
    if not available_expirations:
        return None
    
    # Find the expiration with minimum absolute difference from target
    closest_exp = min(available_expirations, key=lambda x: abs((x - target_date).days))
    
    return closest_exp

def ensure_theta_terminal_running():
    """Check if ThetaTerminal is running, start if needed"""
    try:
        # Quick health check
        response = requests.get(f"{THETADATA_API_BASE}/v2/system/mdds/status", timeout=5)
        if response.text == "CONNECTED":
            print("✅ ThetaTerminal already running and connected")
            return True
    except:
        pass
    
    print("🚀 Starting ThetaTerminal...")
    # Start in background
    subprocess.Popen(["./start_theta.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for connection with timeout
    for i in range(30):  # 30 second timeout
        try:
            response = requests.get(f"{THETADATA_API_BASE}/v2/system/mdds/status", timeout=2)
            if response.text == "CONNECTED":
                print("✅ ThetaTerminal connected successfully")
                return True
        except:
            pass
        if i % 5 == 0 and i > 0:  # Progress update every 5 seconds
            print(f"⏳ Waiting for ThetaTerminal to connect... ({i}s)")
        time.sleep(1)
    
    print("❌ Failed to start ThetaTerminal after 30 seconds")
    print("💡 Please check ThetaTerminal credentials and try again")
    return False

def api_call(cmd: str) -> dict:
    """Make ThetaData API call"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout and not result.stdout.startswith(':'):
            return json.loads(result.stdout)
    except Exception as e:
        print(f"⚠️  ThetaData API error: {str(e)}")
    return {}

def detect_stock_split(symbol: str, entry_date: str, exit_date: str) -> Dict[str, Any]:
    """Detect stock splits"""
    splits = {
        "GOOG": {
            "20220715": {"ratio": 20, "description": "GOOG 20:1 stock split"}
        }
    }
    
    if symbol in splits:
        for split_date, split_info in splits[symbol].items():
            if entry_date <= split_date <= exit_date:
                return {
                    'has_split': True,
                    'split_date': split_date,
                    'split_ratio': split_info['ratio'],
                    'description': split_info['description']
                }
    
    return {'has_split': False}

def get_january_expirations(symbol: str, year: int, entry_date: str) -> List[str]:
    """
    Get all January expirations for the following year.
    Used for the simple "Annual January" strategy.
    """
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/list/expirations?root={symbol}"'
    data = api_call(cmd)
    
    if not data or 'response' not in data:
        return []
    
    entry_dt = datetime.strptime(entry_date, '%Y%m%d')
    target_year = year + 1
    january_exps = []
    
    for exp in data['response']:
        try:
            exp_dt = datetime.strptime(str(exp), '%Y%m%d')
            if exp_dt.year == target_year and exp_dt.month == 1 and exp_dt > entry_dt:
                january_exps.append(str(exp))
        except:
            continue
    
    return sorted(january_exps)

def get_bulk_eod_data(symbol: str, exp: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Get bulk EOD data"""
    print(f"⚡ Bulk EOD: {symbol} {exp} from {start_date} to {end_date}")
    
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/bulk_hist/option/eod?root={symbol}&exp={exp}&start_date={start_date}&end_date={end_date}&rth=true"'
    
    data = api_call(cmd)
    
    if data and 'response' in data:
        print(f"✅ Bulk EOD returned {len(data['response'])} records")
        return data
    
    print("❌ No bulk EOD data available")
    return {}

def get_bulk_eod_greeks(symbol: str, exp: str, date: str) -> Dict[str, Any]:
    """
    Gets bulk End-of-Day greeks data for all strikes for a given expiration and date.
    """
    print(f"📈 Bulk EOD Greeks: {symbol} {exp} on {date}")
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/bulk_hist/option/eod_greeks?root={symbol}&exp={exp}&start_date={date}&end_date={date}"'
    data = api_call(cmd)
    if data and 'response' in data:
        print(f"✅ Bulk EOD Greeks returned {len(data['response'])} records")
        return data
    print(f"❌ No bulk EOD greeks data available for {symbol} {exp} on {date}")
    return {}

def extract_greeks_from_bulk(bulk_greeks: Dict[str, Any], target_strike: int) -> Optional[Dict[str, float]]:
    """
    Extracts greeks for a specific strike from the bulk greeks data response.
    The response format is a list of lists, where each inner list contains tick data.
    The format array specifies the order of the fields.
    Indices used: 15 (delta), 16 (theta), 17 (vega), 21 (gamma), 33 (implied_vol).
    """
    if not bulk_greeks or 'response' not in bulk_greeks:
        return None

    for contract_data in bulk_greeks['response']:
        try:
            contract = contract_data.get('contract', {})
            if contract.get('strike') == target_strike:
                tick = contract_data.get('ticks', [[]])[0]
                if len(tick) >= 34:
                    return {
                        "delta": tick[15],
                        "theta": tick[16],
                        "vega": tick[17],
                        "gamma": tick[21],
                        "iv": tick[33],
                    }
        except (ValueError, IndexError, TypeError):
            continue
    return None

def filter_itm_calls_from_bulk(bulk_data: Dict[str, Any], stock_price: float) -> List[Dict[str, Any]]:
    """Filter ITM calls from bulk EOD data"""
    if not bulk_data or 'response' not in bulk_data:
        return []
    
    valid_calls = []
    stock_price_millidollars = stock_price * 1000
    
    for contract_data in bulk_data['response']:
        try:
            contract = contract_data.get('contract', {})
            ticks = contract_data.get('ticks', [])
            
            if not ticks or not contract:
                continue
                
            strike = contract.get('strike', 0)
            right = contract.get('right', '')
            tick = ticks[0]
            
            if len(tick) < 17:
                continue
                
            close_price = tick[5] if tick[5] else 0
            bid = tick[10] if tick[10] else 0
            ask = tick[14] if tick[14] else 0
            
            # Only process calls
            if right != 'C':
                continue
            
            # Check if ITM
            if strike < stock_price_millidollars:
                # Validate data quality
                if close_price > 0 or (bid > 0 and ask > 0):
                    distance = abs(strike - stock_price_millidollars)
                    valid_calls.append({
                        'strike': strike,
                        'distance': distance,
                        'close': close_price,
                        'bid': bid,
                        'ask': ask,
                        'data_quality': 'excellent' if close_price > 0 else 'good'
                    })
        except (ValueError, IndexError, TypeError):
            continue
    
    # Sort by distance from stock price
    valid_calls.sort(key=lambda x: x['distance'])
    
    print(f"✅ Found {len(valid_calls)} valid ITM calls")
    return valid_calls

def get_bulk_at_time_quotes(symbol: str, exp: str, date: str, target_time_ms: int) -> Dict[str, Any]:
    """Get bulk quotes at exact time"""
    print(f"⚡ Bulk At-Time: {symbol} {exp} at {date} {target_time_ms}ms")
    
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/bulk_at_time/option/quote?root={symbol}&exp={exp}&start_date={date}&end_date={date}&ivl={target_time_ms}&rth=true"'
    
    data = api_call(cmd)
    
    if data and 'response' in data:
        print(f"✅ Bulk At-Time returned {len(data['response'])} quotes")
        return data
    
    print("❌ No bulk at-time data available")
    return {}

def extract_precise_entry_price_from_bulk(bulk_quotes: Dict[str, Any], target_strike: float) -> Optional[float]:
    """Extract precise entry price from bulk quote data"""
    if not bulk_quotes or 'response' not in bulk_quotes:
        return None
    
    for contract_data in bulk_quotes['response']:
        try:
            contract = contract_data.get('contract', {})
            ticks = contract_data.get('ticks', [])
            
            if not ticks or not contract:
                continue
                
            strike = contract.get('strike', 0)
            right = contract.get('right', '')
            tick = ticks[0]
            
            if strike == target_strike and right == 'C' and len(tick) >= 8:
                bid = tick[3] if tick[3] else 0
                ask = tick[7] if tick[7] else 0
                
                if ask > 0:
                    print(f"   ✅ Precise entry price: ${ask:.2f} (ask)")
                    return ask
                elif bid > 0:
                    print(f"   ⚠️  Using bid for entry: ${bid:.2f}")
                    return bid
        except Exception:
            continue
    
    return None

def get_exit_price_individual(symbol: str, exp_date: str, exit_strike: float, exit_date: str) -> Optional[float]:
    """Get exit price using individual EOD call"""
    print(f"📊 Exit pricing: {symbol} {exp_date} ${exit_strike/1000:.2f} on {exit_date}")
    
    cmd = f'curl -s "{THETADATA_API_BASE}/v2/hist/option/eod?root={symbol}&exp={exp_date}&strike={exit_strike}&right=C&start_date={exit_date}&end_date={exit_date}"'
    exit_data = api_call(cmd)
    
    if exit_data and 'response' in exit_data and exit_data['response']:
        exit_record = exit_data['response'][0]
        if len(exit_record) >= 17:
            close_price = exit_record[5] if exit_record[5] else 0
            bid_price = exit_record[10] if exit_record[10] else 0
            
            if close_price > 0:
                print(f"   ✅ Exit price: ${close_price:.2f} (close)")
                return close_price
            elif bid_price > 0:
                print(f"   ✅ Exit price: ${bid_price:.2f} (bid)")
                return bid_price
            elif close_price == 0:
                print(f"   ✅ Exit price: $0.00 (worthless)")
                return 0.0
    
    return None

def find_optimal_leaps_annual_january(symbol: str, year: int, entry_date: str, exit_date: str, stock_price: float) -> Optional[Dict[str, Any]]:
    """
    Finds the optimal LEAP for the "Annual January" strategy.
    It tests all available January expirations for the next year to find the first
    one with a complete and valid data set (entry price, exit price, etc.).
    """
    
    print(f"🎯 ANNUAL JANUARY: Finding January {year+1} LEAPS for {symbol}")
    print(f"📊 STRATEGY: Test each January expiration for complete data validity")
    
    # Get all January expirations for the target year
    january_exps = get_january_expirations(symbol, year, entry_date)
    if not january_exps:
        print(f"❌ No January {year+1} expirations found")
        return None
    
    print(f"📅 Found {len(january_exps)} January {year+1} expirations: {january_exps}")
    
    # Check for stock splits
    split_info = detect_stock_split(symbol, entry_date, exit_date)
    if split_info.get('has_split'):
        print(f"📊 {split_info['description']} detected")
    
    api_call_count = 0
    
    # Test each January expiration sequentially
    for exp_date in january_exps:
        exp_dt = datetime.strptime(exp_date, '%Y%m%d')
        entry_dt = datetime.strptime(entry_date, '%Y%m%d')
        months_out = (exp_dt - entry_dt).days / 30.4375 # Approximation for display
        print(f"\n🎯 Testing expiration: {exp_date} ({months_out:.1f} months out)")
        
        # Step 1: Get bulk EOD data for entry day
        entry_bulk_eod = get_bulk_eod_data(symbol, exp_date, entry_date, entry_date)
        api_call_count += 1
        if not entry_bulk_eod:
            print("❌ No entry EOD data, trying next expiration")
            continue
        
        # Step 2: Filter ITM calls
        valid_itm_calls = filter_itm_calls_from_bulk(entry_bulk_eod, stock_price)
        if not valid_itm_calls:
            print("❌ No valid ITM calls found, trying next expiration")
            continue
        
        # Step 3: Select optimal strike (closest to stock price)
        optimal_call = valid_itm_calls[0]
        original_strike = optimal_call['strike']
        print(f"✅ Selected strike: ${original_strike/1000:.2f}")
        
        # Step 4: Get precise entry pricing with bulk at-time quotes
        entry_quotes = get_bulk_at_time_quotes(symbol, exp_date, entry_date, ENTRY_TIME_MS)
        api_call_count += 1
        entry_price = extract_precise_entry_price_from_bulk(entry_quotes, original_strike)
        
        if not entry_price or entry_price <= 0:
            print("   ❌ No valid entry price at 10:00 AM, trying next expiration")
            continue
        
        # Step 5: Determine exit strike (account for splits)
        exit_strike = original_strike
        if split_info.get('has_split'):
            exit_strike = original_strike // split_info['split_ratio']
            print(f"   🔄 Split adjustment: ${original_strike/1000:.2f} → ${exit_strike/1000:.2f}")
        
        # Step 6: Get exit price
        exit_price = get_exit_price_individual(symbol, exp_date, exit_strike, exit_date)
        api_call_count += 1
        
        if exit_price is None or exit_price < 0:
            print("   ❌ No valid exit price, trying next expiration")
            continue
        
        # Step 7: Get Greeks data for entry and exit
        entry_greeks_data = get_bulk_eod_greeks(symbol, exp_date, entry_date)
        api_call_count += 1
        entry_greeks = extract_greeks_from_bulk(entry_greeks_data, original_strike)
        
        exit_greeks_data = get_bulk_eod_greeks(symbol, exp_date, exit_date)
        api_call_count += 1
        exit_greeks = extract_greeks_from_bulk(exit_greeks_data, exit_strike)
        
        # SUCCESS: Found valid expiration with complete data
        pnl_per_contract = exit_price - entry_price
        pnl_percentage = (pnl_per_contract / entry_price) * 100
        
        print(f"🎉 OPTIMAL LEAPS FOUND!")
        print(f"   API calls used: {api_call_count}")
        print(f"   Entry: ${entry_price:.2f} (precise 10:00 AM)")
        print(f"   Exit: ${exit_price:.2f}")
        print(f"   P&L: ${pnl_per_contract:.2f} ({pnl_percentage:+.1f}%)")
        
        return {
            'expiration': exp_date,
            'months_to_exp': months_out,
            'original_strike': original_strike,
            'exit_strike': exit_strike,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_per_contract': pnl_per_contract,
            'return_pct': pnl_percentage,
            'split_info': split_info,
            'optimization_level': 'accurate_optimized',
            'api_calls_used': api_call_count,
            'expiration_tested': exp_date,
            'total_expirations_available': len(january_exps),
            'entry_greeks': entry_greeks,
            'exit_greeks': exit_greeks
        }
    
    print(f"❌ No valid January LEAPS found after testing all {len(january_exps)} expirations")
    print(f"   Total API calls used: {api_call_count}")
    return None

def analyze_year_annual_january(year: int) -> Optional[Dict[str, Any]]:
    """Analyze a single year for the 'Annual January' strategy."""
    print(f"\n📊 ANNUAL JANUARY ANALYSIS: {year}")
    print("="*80)
    
    # Market days (ThetaData cache - no API calls after first fetch)
    entry_date = get_first_trading_day_of_year("GOOG", year)
    
    # For current year, use most recent available trading day; for past years, use last trading day
    current_year = datetime.now().year
    if year == current_year:
        # Use most recent trading day with available data
        exit_date = get_most_recent_trading_day("GOOG")
        print(f"📅 Using most recent trading day for current year: {exit_date}")
    else:
        exit_date = get_last_trading_day_of_year("GOOG", year)
    
    if not entry_date or not exit_date:
        return None
    
    print(f"Entry: {entry_date}")
    print(f"Exit: {exit_date}")
    
    # Stock price (cached - no API calls)
    stock_price = get_stock_price_with_smart_fallback("GOOG", entry_date)
    if not stock_price:
        return None
    
    print(f"Stock price: ${stock_price:.2f}")
    
    # Find optimal LEAPS with accurate validation
    start_time = time.time()
    result = find_optimal_leaps_annual_january("GOOG", year, entry_date, exit_date, stock_price)
    analysis_time = time.time() - start_time
    
    if not result:
        print(f"⏱️  Analysis time: {analysis_time:.2f} seconds")
        return None
    
    result.update({
        'year': year,
        'analysis_time': analysis_time,
        'entry_date': entry_date,
        'exit_date': exit_date,
        'stock_price_entry': stock_price
    })
    
    print(f"✅ SUCCESS - Analysis time: {analysis_time:.2f} seconds")
    return result


def execute_single_quarterly_trade(symbol: str, entry_date: str, exit_date: str, 
                                 stock_price: float, fixed_strike: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Executes a single quarterly LEAPS trade.
    This function finds the best LEAP option with an expiration ~15 months out,
    buys it, and returns the result.
    """
    
    print(f"\n🔄 Quarterly Trade: {entry_date} → {exit_date}")
    
    # Convert entry date and calculate 15-month target using approximation
    entry_dt = datetime.strptime(entry_date, '%Y%m%d').date()
    target_15_months = entry_dt + relativedelta(months=15)
    one_year_later = entry_dt + timedelta(days=365) # Min expiration for a LEAP
    
    print(f"📅 Entry Date: {entry_dt}")
    print(f"📅 Target 15-month date: {target_15_months}")
    
    # Get all historically available expirations on the entry date
    all_available_expirations = get_expirations_available_on_date(symbol, entry_date)
    if not all_available_expirations:
        print("❌ No expirations found for entry date")
        return None
    
    # Filter for LEAPS-qualifying expirations (must be at least 1 year out)
    leaps_expirations = [exp for exp in all_available_expirations if exp >= one_year_later]
    
    if not leaps_expirations:
        print("❌ No LEAPS-qualifying expirations found (≥1 year)")
        return None
    
    print(f"✅ Found {len(leaps_expirations)} LEAPS-qualifying expirations")
    
    # Find the actual expiration date closest to our 15-month target
    closest_expiration_obj = find_closest_expiration_date(leaps_expirations, target_15_months)
    if not closest_expiration_obj:
        print("❌ No suitable expiration found")
        return None
    
    exp_date = closest_expiration_obj.strftime('%Y%m%d')
    months_out = (closest_expiration_obj - entry_dt).days / 30.4375 # Approximation for display
    deviation_days = abs((closest_expiration_obj - target_15_months).days)
    
    print(f"✅ Selected expiration: {exp_date} ({months_out:.1f} months, ±{deviation_days} days from target)")
    
    # Check for stock splits during the trade period
    split_info = detect_stock_split(symbol, entry_date, exit_date)
    if split_info.get('has_split'):
        print(f"📊 {split_info['description']} detected")
    
    # Get bulk EOD data for entry day to find ITM calls
    entry_bulk_eod = get_bulk_eod_data(symbol, exp_date, entry_date, entry_date)
    if not entry_bulk_eod:
        print("❌ No entry EOD data available")
        return None
    
    # Filter for valid In-The-Money (ITM) calls
    valid_itm_calls = filter_itm_calls_from_bulk(entry_bulk_eod, stock_price)
    if not valid_itm_calls:
        print("❌ No valid ITM calls found")
        return None
    
    # Select strike (either fixed from previous quarter or the optimal one)
    if fixed_strike:
        # Find the specified fixed strike from the previous trade
        optimal_call = next((c for c in valid_itm_calls if c['strike'] == fixed_strike), None)
        if not optimal_call:
            print(f"❌ Fixed strike ${fixed_strike/1000:.2f} not available")
            return None
    else:
        # Select the optimal strike (closest to the stock price)
        optimal_call = valid_itm_calls[0]
    
    original_strike = optimal_call['strike']
    print(f"✅ Selected strike: ${original_strike/1000:.2f}")
    
    # Get precise entry pricing at 10:00 AM
    entry_quotes = get_bulk_at_time_quotes(symbol, exp_date, entry_date, ENTRY_TIME_MS)
    entry_price = extract_precise_entry_price_from_bulk(entry_quotes, original_strike)
    
    if not entry_price or entry_price <= 0:
        print("❌ No valid entry price available")
        return None
    
    # Determine exit strike (account for stock splits)
    exit_strike = original_strike
    if split_info.get('has_split'):
        exit_strike = original_strike // split_info['split_ratio']
        print(f"   🔄 Split adjustment: ${original_strike/1000:.2f} → ${exit_strike/1000:.2f}")
    
    # Get exit price at the end of the quarter
    exit_price = get_exit_price_individual(symbol, exp_date, exit_strike, exit_date)
    if exit_price is None or exit_price < 0:
        print("❌ No valid exit price available")
        return None
    
    # Get Greeks data for entry and exit
    entry_greeks_data = get_bulk_eod_greeks(symbol, exp_date, entry_date)
    entry_greeks = extract_greeks_from_bulk(entry_greeks_data, original_strike)
    
    exit_greeks_data = get_bulk_eod_greeks(symbol, exp_date, exit_date)
    exit_greeks = extract_greeks_from_bulk(exit_greeks_data, exit_strike)
    
    # --- Trade successful, calculate results ---
    pnl_per_contract = exit_price - entry_price
    pnl_percentage = (pnl_per_contract / entry_price) * 100 if entry_price > 0 else 0
    
    entry_dt_datetime = datetime.strptime(entry_date, '%Y%m%d')
    exit_dt = datetime.strptime(exit_date, '%Y%m%d')
    hold_days = (exit_dt - entry_dt_datetime).days
    
    print(f"✅ Quarterly trade completed:")
    print(f"   Entry: ${entry_price:.2f} → Exit: ${exit_price:.2f}")
    print(f"   P&L: ${pnl_per_contract:.2f} ({pnl_percentage:+.1f}%)")
    print(f"   Hold period: {hold_days} days")
    
    return {
        'entry_date': entry_date,
        'exit_date': exit_date,
        'expiration': exp_date,
        'months_to_exp': months_out,
        'original_strike': original_strike,
        'exit_strike': exit_strike,
        'strike': original_strike,  # For backwards compatibility
        'entry_price': entry_price,
        'exit_price': exit_price,
        'pnl_per_contract': pnl_per_contract,
        'return_pct': pnl_percentage,
        'hold_days': hold_days,
        'split_info': split_info,
        'target_15_months': target_15_months.strftime('%Y%m%d'),
        'deviation_days': deviation_days,
        'entry_greeks': entry_greeks,
        'exit_greeks': exit_greeks
    }

def analyze_quarterly_strategy(symbol: str, year: int, use_fixed_strikes: bool = False) -> Optional[Dict[str, Any]]:
    """Analyze the quarterly rolling LEAPS strategy for a full year."""
    
    print(f"\n🔄 QUARTERLY ROLLING LEAPS ANALYSIS: {year}")
    print("="*80)
    
    # Define the trading schedule for the year
    q1_start = get_first_trading_day_of_year(symbol, year)
    q1_end = get_last_trading_day_of_quarter(symbol, year, 1)
    q2_end = get_last_trading_day_of_quarter(symbol, year, 2)
    q3_end = get_last_trading_day_of_quarter(symbol, year, 3)
    q4_end = get_last_trading_day_of_quarter(symbol, year, 4)
    
    # For the current year, the backtest only runs up to the most recent trading day
    current_year = datetime.now().year
    if year == current_year:
        year_end = get_most_recent_trading_day(symbol)
        print(f"📅 Using most recent trading day for current year: {year_end}")
        q4_end = year_end
    
    # Define the sequence of trades for the year
    trade_schedule = [
        {'quarter': 'Q1', 'entry': q1_start, 'exit': q1_end},
        {'quarter': 'Q2', 'entry': q1_end,   'exit': q2_end},
        {'quarter': 'Q3', 'entry': q2_end,   'exit': q3_end},
        {'quarter': 'Q4', 'entry': q3_end,   'exit': q4_end},
    ]
    
    print("Quarterly Trading Schedule:")
    for item in trade_schedule:
        print(f"  {item['quarter']}: {item['entry']} → {item['exit']}")
        
    if not all([q1_start, q1_end, q2_end, q3_end]):
        print("❌ Could not get minimum required trading days (Q1-Q3)")
        return None
    
    trades = []
    yearly_pnl = 0.0
    fixed_strike = None
    
    # Execute each quarterly trade in sequence
    for trade_info in trade_schedule:
        entry = trade_info['entry']
        exit_ = trade_info['exit']
        
        if not entry or not exit_:
            continue
            
        print(f"\n📊 {trade_info['quarter']} Position ({entry} → {exit_}):")
        stock_price = get_stock_price_with_smart_fallback(symbol, entry)
        
        if stock_price:
            trade_result = execute_single_quarterly_trade(symbol, entry, exit_, 
                                                          stock_price, fixed_strike)
            if trade_result:
                trades.append({**trade_result, 'quarter': trade_info['quarter']})
                yearly_pnl += trade_result['pnl_per_contract']
                
                # If using fixed strikes, lock in the strike from the first successful trade
                if use_fixed_strikes and fixed_strike is None:
                    fixed_strike = trade_result['strike']
                    print(f"🔒 Fixed strike set for year: ${fixed_strike/1000:.2f}")

    if not trades:
        return None
    
    # --- Calculate yearly summary ---
    winning_trades = sum(1 for trade in trades if trade['pnl_per_contract'] > 0)
    total_investment = sum(trade['entry_price'] for trade in trades)
    yearly_return_pct = (yearly_pnl / total_investment) * 100 if total_investment > 0 else 0
    avg_hold_days = sum(trade['hold_days'] for trade in trades) / len(trades)
    
    # Analyze consistency of the 15-month targeting
    months_list = [trade['months_to_exp'] for trade in trades]
    deviations = [trade.get('deviation_days', 0) for trade in trades]
    avg_months = sum(months_list) / len(months_list)
    max_deviation = max(deviations) if deviations else 0
    
    # --- New Greeks Analysis ---
    entry_deltas = [t['entry_greeks']['delta'] for t in trades if t.get('entry_greeks') and t['entry_greeks']]
    exit_deltas = [t['exit_greeks']['delta'] for t in trades if t.get('exit_greeks') and t['exit_greeks']]
    entry_ivs = [t['entry_greeks']['iv'] for t in trades if t.get('entry_greeks') and t['entry_greeks']]
    exit_ivs = [t['exit_greeks']['iv'] for t in trades if t.get('exit_greeks') and t['exit_greeks']]

    avg_entry_delta = sum(entry_deltas) / len(entry_deltas) if entry_deltas else 0
    avg_exit_delta = sum(exit_deltas) / len(exit_deltas) if exit_deltas else 0
    avg_entry_iv = sum(entry_ivs) / len(entry_ivs) if entry_ivs else 0
    avg_exit_iv = sum(exit_ivs) / len(exit_ivs) if exit_ivs else 0
    
    print(f"\n📈 15-Month Targeting Analysis:")
    print(f"   Average months to expiration: {avg_months:.1f}")
    print(f"   Max deviation from 15M target: {max_deviation} days")
    
    return {
        'year': year,
        'strategy': 'quarterly_rolling_leaps_15month',
        'trades': trades,
        'yearly_summary': {
            'total_trades': len(trades),
            'winning_trades': winning_trades,
            'total_pnl': yearly_pnl,
            'total_investment': total_investment,
            'yearly_return_pct': yearly_return_pct,
            'avg_hold_days': avg_hold_days,
            'avg_months_to_exp': avg_months,
            'max_deviation_days': max_deviation,
            'avg_entry_delta': avg_entry_delta,
            'avg_exit_delta': avg_exit_delta,
            'avg_entry_iv': avg_entry_iv,
            'avg_exit_iv': avg_exit_iv
        },
        'use_fixed_strikes': use_fixed_strikes,
        'quarter_schedule': {
            'q1_period': f"{q1_start} → {q1_end}",
            'q2_period': f"{q1_end} → {q2_end}",
            'q3_period': f"{q2_end} → {q3_end}",
            'q4_period': f"{q3_end} → {q4_end}"
        }
    }

def display_comparison_results(annual_results: List[Dict], quarterly_results: List[Dict]) -> None:
    """Displays a detailed, side-by-side comparison of the two strategies, including greeks."""
    print(f"\n\n🆚 STRATEGY DEEP DIVE: ANNUAL vs. QUARTERLY ROLLING LEAPS")
    print("=" * 120)
    print("This analysis compares the simple Annual-Hold strategy against the Quarterly Rolling strategy.")
    print("Greeks (Delta, IV) are shown at the point of entry and exit to reveal how each strategy performs under different market conditions.")
    print("-" * 120)

    header = (
        f"{'Year':<6} | {'Strategy':<11} | {'Return':>8} | {'Entry Δ':>8} | {'Exit Δ':>8} | "
        f"{'Entry IV':>8} | {'Exit IV':>8} | {'Trades':>7} | {'Win Rate':>9}"
    )
    print(header)
    print("-" * 120)

    all_years = sorted(list(set([r['year'] for r in annual_results] + [r['year'] for r in quarterly_results])))

    for year in all_years:
        # --- Annual Data ---
        annual_data = next((r for r in annual_results if r['year'] == year), None)
        if annual_data:
            entry_greeks = annual_data.get('entry_greeks') or {}
            exit_greeks = annual_data.get('exit_greeks') or {}
            annual_str = (
                f"{year:<6} | {'Annual':<11} | {annual_data.get('return_pct', 0):>7.1f}% | "
                f"{entry_greeks.get('delta', 0):>8.2f} | {exit_greeks.get('delta', 0):>8.2f} | "
                f"{entry_greeks.get('iv', 0):>8.3f} | {exit_greeks.get('iv', 0):>8.3f} | {'1':>7} | {'100.0%' if annual_data.get('return_pct', 0) > 0 else '0.0%' :>9}"
            )
            print(annual_str)

        # --- Quarterly Data ---
        quarterly_data = next((r for r in quarterly_results if r['year'] == year), None)
        if quarterly_data:
            summary = quarterly_data['yearly_summary']
            win_rate = (summary['winning_trades'] / summary['total_trades']) * 100 if summary['total_trades'] > 0 else 0
            quarterly_str = (
                f"{'':<6} | {'Quarterly':<11} | {summary.get('yearly_return_pct', 0):>7.1f}% | "
                f"{summary.get('avg_entry_delta', 0):>8.2f} | {summary.get('avg_exit_delta', 0):>8.2f} | "
                f"{summary.get('avg_entry_iv', 0):>8.3f} | {summary.get('avg_exit_iv', 0):>8.3f} | {summary['total_trades']:>7} | {win_rate:>8.1f}%"
            )
            print(quarterly_str)
        
        print("-" * 120)

    # Summary statistics
    print("\n📊 SUMMARY STATISTICS")
    print("-" * 50)
    
    annual_returns = [r.get('return_pct', 0) for r in annual_results if r.get('return_pct') is not None]
    quarterly_returns = [r['yearly_summary']['yearly_return_pct'] for r in quarterly_results if r]
    
    if annual_returns:
        annual_avg = sum(annual_returns) / len(annual_returns)
        annual_wins = sum(1 for r in annual_returns if r > 0)
        print(f"Annual Strategy:")
        print(f"  Average Return: {annual_avg:+.1f}%")
        print(f"  Win Rate: {annual_wins}/{len(annual_returns)} ({annual_wins/len(annual_returns)*100:.1f}%)")
    
    if quarterly_returns:
        quarterly_avg = sum(quarterly_returns) / len(quarterly_returns)
        quarterly_total_trades = sum(r['yearly_summary']['total_trades'] for r in quarterly_results if r)
        quarterly_winning_trades = sum(r['yearly_summary']['winning_trades'] for r in quarterly_results if r)
        print(f"Quarterly Strategy:")
        print(f"  Average Return: {quarterly_avg:+.1f}%")
        print(f"  Total Trades: {quarterly_total_trades}")
        print(f"  Winning Trades: {quarterly_winning_trades}/{quarterly_total_trades} ({quarterly_winning_trades/quarterly_total_trades*100:.1f}%)")

def main():
    """Main function to run the backtesting strategies"""
    
    parser = argparse.ArgumentParser(description='LEAPS Strategy Backtesting')
    parser.add_argument('--strategy', choices=['annual', 'quarterly', 'both'], 
                       default='both', help='Strategy to test (default: both)')
    parser.add_argument('--use-fixed-strikes', action='store_true',
                       help='Use the same strike price for all quarterly trades within a single year')
    args = parser.parse_args()
    
    print("🎯 LEAPS STRATEGY BACKTESTING SYSTEM")
    print("=" * 80)
    
    if not ensure_theta_terminal_running():
        print("💡 Please ensure ThetaTerminal credentials are configured correctly")
        return
    
    current_year = datetime.now().year
    years = list(range(2016, current_year + 1))
    print(f"📅 Testing years: {years[0]} to {years[-1]} ({len(years)} years)")
    
    if args.use_fixed_strikes:
        print("🔒 Using fixed strike prices for the quarterly strategy")
    
    print("=" * 80)
    
    annual_results = []
    quarterly_results = []
    
    # --- Run Annual January Strategy ---
    if args.strategy in ['annual', 'both']:
        print("\n🎯 ANNUAL JANUARY LEAPS STRATEGY")
        print("📊 Buy a single January LEAP and hold for the entire year.")
        print("-" * 80)
        
        for year in years:
            result = analyze_year_annual_january(year)
            if result:
                annual_results.append(result)
        
        if annual_results:
            print("\n📈 ANNUAL STRATEGY RESULTS:")
            for r in annual_results:
                print(f"{r['year']}: {r.get('return_pct', 0):+.1f}% "
                      f"(API calls: {r.get('api_calls_used', 0)})")
    
    # --- Run Quarterly Rolling 15-Month Strategy ---
    if args.strategy in ['quarterly', 'both']:
        print("\n🔄 QUARTERLY ROLLING 15-MONTH LEAPS STRATEGY")
        print("📊 Buy a ~15-month LEAP and roll it at the end of each quarter.")
        print("-" * 80)
        
        for year in years:
            result = analyze_quarterly_strategy("GOOG", year, args.use_fixed_strikes)
            if result:
                quarterly_results.append(result)
                
                # Display results for the year
                summary = result['yearly_summary']
                print(f"\n{year} Quarterly Results:")
                print(f"   Total Return: {summary['yearly_return_pct']:+.1f}%")
                print(f"   Trades: {summary['total_trades']} "
                      f"(Wins: {summary['winning_trades']})")
                print(f"   Average Hold: {summary['avg_hold_days']:.0f} days")
                
                for trade in result['trades']:
                    print(f"   {trade['quarter']}: {trade['return_pct']:+.1f}% "
                          f"({trade['hold_days']} days)")
    
    # --- Display final comparison ---
    if args.strategy == 'both' and annual_results and quarterly_results:
        display_comparison_results(annual_results, quarterly_results)
    
    print(f"\n✅ BACKTESTING COMPLETE")
    print(f"📊 Strategy: {args.strategy.title()}")
    if args.use_fixed_strikes and args.strategy in ['quarterly', 'both']:
        print(f"🔒 Fixed strikes: Enabled")
    print("=" * 80)

if __name__ == "__main__":
    main()

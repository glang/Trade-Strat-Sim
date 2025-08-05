#!/usr/bin/env python3
"""
Quarterly Rolling LEAPS Backtester (Refactored for Quiet Mode)

This script backtests two LEAPS (Long-term Equity AnticiPation Securities) strategies.

This version has been refactored to support a `quiet` flag, allowing the
verbose output from its functions to be suppressed when called by other scripts.
"""

import subprocess
import json
import time
import os
import requests
import httpx
import argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Tuple, Optional, Any

# Import smart caching functions
from .smart_leaps_backtest import (
    get_stock_price_with_smart_fallback,
    analyze_smart_cache
)

# Import ThetaData market days cache system
from .market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_most_recent_trading_day,
    get_first_trading_day_of_quarter,
    get_last_trading_day_of_quarter
)

# --- Constants ---
THETADATA_API_BASE = "http://localhost:25503/v3"
ENTRY_TIME_MS = 36000000  # 10:00 AM EST for precise entry price

def format_date_for_api(date_str: str) -> str:
    """Convert YYYYMMDD format to YYYY-MM-DD format for API calls"""
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str  # Already in correct format or other format

def get_expirations_available_on_date(symbol: str, date_str: str, quiet: bool = False) -> List[datetime.date]:
    if not quiet: print(f"🔍 Getting available expirations for {symbol} on {date_str}")
    
    # Use v3 API endpoint with httpx
    url = f"{THETADATA_API_BASE}/option/list/expirations"
    params = {"symbol": symbol, "format": "json"}
    data = api_call(url, params, quiet=quiet)
    
    # Since the new endpoint doesn't filter by date, we'd need a way to check tradable contracts for that day.
    # This is a placeholder for a more complex logic that might be needed.
    # For now, we assume all listed expirations were available.
    if not data or 'expiration' not in data:
        if not quiet: print(f"❌ No expirations returned for {symbol}")
        return []
    
    expiration_set = set()
    for exp_str in data['expiration']:
        try:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            expiration_set.add(exp_date)
        except (ValueError, TypeError):
            continue
            
    expirations = sorted(list(expiration_set))
    if not quiet: print(f"✅ Found {len(expirations)} unique expiration dates")
    return expirations

def find_closest_expiration_date(available_expirations: List[datetime.date], target_date: datetime.date) -> Optional[datetime.date]:
    if not available_expirations:
        return None
    closest_exp = min(available_expirations, key=lambda x: abs((x - target_date).days))
    return closest_exp

def ensure_theta_terminal_running(quiet: bool = False) -> bool:
    """
    DEPRECATED: Use theta_connection_manager.ensure_theta_terminal_connected() instead.
    
    This function is kept for backward compatibility but will be removed in future versions.
    """
    import warnings
    warnings.warn(
        "ensure_theta_terminal_running() is deprecated. "
        "Use theta_connection_manager.ensure_theta_terminal_connected() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    from .theta_connection_manager import ensure_theta_terminal_connected
    return ensure_theta_terminal_connected(quiet=quiet)

def api_call(url: str, params: dict = None, quiet: bool = False) -> dict:
    """Make an HTTP request to ThetaData API using httpx"""
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            
            if response.text and not response.text.startswith(':'):
                # Check for JSON array response
                if response.text.strip().startswith('[') and response.text.strip().endswith(']'):
                    # Handle simple JSON array of strings (like expirations)
                    parsed_data = response.json()
                    if all(isinstance(item, str) for item in parsed_data):
                        return {'expiration': parsed_data}  # Wrap in a dict to match expected structure
                    return {'response': parsed_data}  # Otherwise, wrap in response key
                # Assume JSON object response
                return response.json()
    except Exception as e:
        if not quiet: print(f"⚠️  ThetaData API error: {str(e)}")
    return {}

def api_call_csv(url: str, params: dict = None, quiet: bool = False) -> list:
    """Make an HTTP request to ThetaData API using httpx and parse CSV response"""
    import csv
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            
            # Parse CSV response as per documentation
            csv_reader = csv.reader(response.text.split("\n"))
            data = []
            for row in csv_reader:
                if row:  # Skip empty rows
                    data.append(row)
            return data
    except Exception as e:
        if not quiet: print(f"⚠️  ThetaData API error: {str(e)}")
    return []

def detect_stock_split(symbol: str, entry_date: str, exit_date: str) -> Dict[str, Any]:
    splits = {"GOOG": {"20220715": {"ratio": 20, "description": "GOOG 20:1 stock split"}}}
    if symbol in splits:
        for split_date, split_info in splits[symbol].items():
            if entry_date <= split_date <= exit_date:
                return {'has_split': True, 'split_date': split_date, 'split_ratio': split_info['ratio'], 'description': split_info['description']}
    return {'has_split': False}

def get_january_expirations(symbol: str, year: int, entry_date: str, quiet: bool = False) -> List[str]:
    url = f"{THETADATA_API_BASE}/option/list/expirations"
    params = {"symbol": symbol, "format": "json"}
    data = api_call(url, params, quiet=quiet)
    if not data or 'expiration' not in data:
        return []
    
    entry_dt = datetime.strptime(entry_date, '%Y%m%d')
    target_year = year + 1
    january_exps = []

    for exp_str in data['expiration']:
        try:
            # New format is YYYY-MM-DD
            exp_dt = datetime.strptime(exp_str, '%Y-%m-%d')
            if exp_dt.year == target_year and exp_dt.month == 1 and exp_dt > entry_dt:
                # Convert back to YYYYMMDD for consistency in the rest of the script
                january_exps.append(exp_dt.strftime('%Y%m%d'))
        except ValueError:
            continue
            
    return sorted(january_exps)

def get_bulk_eod_data(symbol: str, exp: str, start_date: str, end_date: str, quiet: bool = False) -> Dict[str, Any]:
    if not quiet: print(f"⚡ Bulk EOD: {symbol} {exp} from {start_date} to {end_date}")
    url = f"{THETADATA_API_BASE}/option/history/eod"
    # Convert expiration and dates to proper format
    exp_formatted = format_date_for_api(exp)
    start_formatted = format_date_for_api(start_date)
    end_formatted = format_date_for_api(end_date)
    
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "start_date": start_formatted,
        "end_date": end_formatted
    }
    # Use CSV format as per documentation
    response = api_call_csv(url, params, quiet=quiet)
    if response:
        if not quiet: print(f"✅ Bulk EOD returned {len(response)} records")
        return {'response': response}
    if not quiet: print("❌ No bulk EOD data available")
    return {}

def get_bulk_eod_greeks(symbol: str, exp: str, date: str, quiet: bool = False) -> Dict[str, Any]:
    if not quiet: print(f"📈 Bulk EOD Greeks: {symbol} {exp} on {date}")
    url = f"{THETADATA_API_BASE}/option/history/greeks/eod"
    # Convert expiration and date to proper format  
    exp_formatted = format_date_for_api(exp)
    date_formatted = format_date_for_api(date)
    
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "start_date": date_formatted,
        "end_date": date_formatted
    }
    # Use CSV format as per documentation
    response = api_call_csv(url, params, quiet=quiet)
    if response:
        if not quiet: print(f"✅ Bulk EOD Greeks returned {len(response)} records")
        return {'response': response}
    if not quiet: print(f"❌ No bulk EOD greeks data available for {symbol} {exp} on {date}")
    return {}

def extract_greeks_from_bulk(bulk_greeks: Dict[str, Any], target_strike: int) -> Optional[Dict[str, float]]:
    if not bulk_greeks or 'response' not in bulk_greeks: return None
    
    # CSV format: each row is a list of strings
    for row in bulk_greeks['response']:
        try:
            if len(row) < 34: continue
            # Parse CSV fields - adjust indices based on actual CSV format for Greeks
            strike = float(row[3])  # Strike price
            if strike == target_strike:
                delta = float(row[15]) if row[15] else 0
                theta = float(row[16]) if row[16] else 0
                vega = float(row[17]) if row[17] else 0
                gamma = float(row[21]) if row[21] else 0
                iv = float(row[33]) if row[33] else 0
                return {"delta": delta, "theta": theta, "vega": vega, "gamma": gamma, "iv": iv}
        except (ValueError, IndexError, TypeError):
            continue
    return None

def filter_itm_calls_from_bulk(bulk_data: Dict[str, Any], stock_price: float, quiet: bool = False) -> List[Dict[str, Any]]:
    if not bulk_data or 'response' not in bulk_data: return []
    valid_calls = []
    stock_price_dollars = stock_price  # Stock price in dollars, not millidollars
    
    # CSV format: skip header row if present
    rows = bulk_data['response']
    start_index = 1 if rows and rows[0][0] == 'symbol' else 0
    
    for row in rows[start_index:]:
        try:
            if len(row) < 19: continue
            # Parse CSV fields based on actual CSV format from ThetaData v3 API
            # Columns: symbol,expiration,strike,right,created,last_trade,open,high,low,close,volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
            strike = float(row[2])  # Strike price (column 2)
            right = row[3]  # Option type (column 3: PUT/CALL)
            close_price = float(row[9]) if row[9] else 0  # Close price (column 9)
            bid = float(row[14]) if row[14] else 0  # Bid price (column 14)
            ask = float(row[18]) if row[18] else 0  # Ask price (column 18)
            
            if right != 'CALL': continue
            if strike < stock_price_dollars:
                if close_price > 0 or (bid > 0 and ask > 0):
                    distance = abs(strike - stock_price_dollars)
                    # Convert to millidollars for consistency with existing code
                    strike_millidollars = strike * 1000
                    valid_calls.append({'strike': strike_millidollars, 'distance': distance * 1000, 'close': close_price, 'bid': bid, 'ask': ask, 'data_quality': 'excellent' if close_price > 0 else 'good'})
        except (ValueError, IndexError, TypeError):
            continue
    valid_calls.sort(key=lambda x: x['distance'])
    if not quiet: print(f"✅ Found {len(valid_calls)} valid ITM calls")
    return valid_calls

def get_bulk_at_time_quotes(symbol: str, exp: str, date: str, target_time_ms: int, quiet: bool = False) -> Dict[str, Any]:
    if not quiet: print(f"⚡ Bulk At-Time: {symbol} {exp} at {date} {target_time_ms}ms")
    
    # Convert milliseconds to HH:MM:SS.mmm format for v3 API
    hours = target_time_ms // 3600000
    minutes = (target_time_ms % 3600000) // 60000
    seconds = (target_time_ms % 60000) // 1000
    milliseconds = target_time_ms % 1000
    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    # Convert expiration and date to proper format
    exp_formatted = format_date_for_api(exp)
    date_formatted = format_date_for_api(date)
    
    url = f"{THETADATA_API_BASE}/option/at_time/quote"
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "start_date": date_formatted,
        "end_date": date_formatted,
        "time_of_day": time_str
    }
    # Use CSV format as per documentation
    response = api_call_csv(url, params, quiet=quiet)
    if response:
        if not quiet: print(f"✅ Bulk At-Time returned {len(response)} quotes")
        return {'response': response}
    if not quiet: print("❌ No bulk at-time data available")
    return {}

def extract_precise_entry_price_from_bulk(bulk_quotes: Dict[str, Any], target_strike: float, quiet: bool = False) -> Optional[float]:
    if not bulk_quotes or 'response' not in bulk_quotes: return None
    
    # CSV format: skip header row if present
    rows = bulk_quotes['response']
    start_index = 1 if rows and rows[0][0] == 'symbol' else 0
    target_strike_dollars = target_strike / 1000  # Convert from millidollars to dollars
    
    for row in rows[start_index:]:
        try:
            if len(row) < 13: continue
            # Parse CSV fields based on actual CSV format for at-time quotes
            # Columns: symbol,expiration,strike,right,timestamp,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
            strike = float(row[2])  # Strike price (column 2)
            right = row[3]  # Option type (column 3: PUT/CALL)
            
            if abs(strike - target_strike_dollars) < 0.01 and right == 'CALL':
                bid = float(row[7]) if row[7] else 0  # Bid price (column 7)
                ask = float(row[11]) if row[11] else 0  # Ask price (column 11)
                if ask > 0:
                    if not quiet: print(f"   ✅ Precise entry price: ${ask:.2f} (ask)")
                    return ask
                elif bid > 0:
                    if not quiet: print(f"   ⚠️  Using bid for entry: ${bid:.2f}")
                    return bid
        except Exception:
            continue
    return None

def get_exit_price_individual(symbol: str, exp_date: str, exit_strike: float, exit_date: str, quiet: bool = False) -> Optional[float]:
    if not quiet: print(f"📊 Exit pricing: {symbol} {exp_date} ${exit_strike/1000:.2f} on {exit_date}")
    url = f"{THETADATA_API_BASE}/option/history/eod"
    # Convert expiration and date to proper format
    exp_formatted = format_date_for_api(exp_date)
    date_formatted = format_date_for_api(exit_date)
    
    # Use bulk approach without specifying strike/right to avoid 472 errors
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "start_date": date_formatted,
        "end_date": date_formatted
    }
    # Use CSV format as per documentation
    response = api_call_csv(url, params, quiet=quiet)
    if response and len(response) > 1:  # Check we have more than just header
        exit_strike_dollars = exit_strike / 1000  # Convert from millidollars to dollars
        
        # Skip header row
        for row in response[1:]:
            if len(row) >= 19:
                # Parse CSV fields based on EOD format
                # Columns: symbol,expiration,strike,right,created,last_trade,open,high,low,close,volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
                strike = float(row[2])
                right = row[3]
                close_price = float(row[9]) if row[9] else 0
                bid_price = float(row[14]) if row[14] else 0
                
                if abs(strike - exit_strike_dollars) < 0.01 and right == 'CALL':
                    if close_price > 0:
                        if not quiet: print(f"   ✅ Exit price: ${close_price:.2f} (close)")
                        return close_price
                    elif bid_price > 0:
                        if not quiet: print(f"   ✅ Exit price: ${bid_price:.2f} (bid)")
                        return bid_price
                    elif close_price == 0:
                        if not quiet: print(f"   ✅ Exit price: $0.00 (worthless)")
                        return 0.0
    return None

def find_optimal_leaps_annual_january(symbol: str, year: int, entry_date: str, exit_date: str, stock_price: float, quiet: bool = False) -> Optional[Dict[str, Any]]:
    if not quiet:
        print(f"🎯 ANNUAL JANUARY: Finding January {year+1} LEAPS for {symbol}")
        print(f"📊 STRATEGY: Test each January expiration for complete data validity")
    january_exps = get_january_expirations(symbol, year, entry_date, quiet=quiet)
    if not january_exps:
        if not quiet: print(f"❌ No January {year+1} expirations found")
        return None
    if not quiet: print(f"📅 Found {len(january_exps)} January {year+1} expirations: {january_exps}")
    split_info = detect_stock_split(symbol, entry_date, exit_date)
    if not quiet and split_info.get('has_split'):
        print(f"📊 {split_info['description']} detected")
    api_call_count = 0
    for exp_date in january_exps:
        exp_dt = datetime.strptime(exp_date, '%Y%m%d')
        entry_dt = datetime.strptime(entry_date, '%Y%m%d')
        months_out = (exp_dt - entry_dt).days / 30.4375
        if not quiet: print(f"\n🎯 Testing expiration: {exp_date} ({months_out:.1f} months out)")
        entry_bulk_eod = get_bulk_eod_data(symbol, exp_date, entry_date, entry_date, quiet=quiet)
        api_call_count += 1
        if not entry_bulk_eod:
            if not quiet: print("❌ No entry EOD data, trying next expiration")
            continue
        valid_itm_calls = filter_itm_calls_from_bulk(entry_bulk_eod, stock_price, quiet=quiet)
        if not valid_itm_calls:
            if not quiet: print("❌ No valid ITM calls found, trying next expiration")
            continue
        optimal_call = valid_itm_calls[0]
        original_strike = optimal_call['strike']
        if not quiet: print(f"✅ Selected strike: ${original_strike/1000:.2f}")
        entry_quotes = get_bulk_at_time_quotes(symbol, exp_date, entry_date, ENTRY_TIME_MS, quiet=quiet)
        api_call_count += 1
        entry_price = extract_precise_entry_price_from_bulk(entry_quotes, original_strike, quiet=quiet)
        if not entry_price or entry_price <= 0:
            if not quiet: print("   ❌ No valid entry price at 10:00 AM, trying next expiration")
            continue
        exit_strike = original_strike
        if split_info.get('has_split'):
            exit_strike = original_strike // split_info['split_ratio']
            if not quiet: print(f"   🔄 Split adjustment: ${original_strike/1000:.2f} → ${exit_strike/1000:.2f}")
        exit_price = get_exit_price_individual(symbol, exp_date, exit_strike, exit_date, quiet=quiet)
        api_call_count += 1
        if exit_price is None or exit_price < 0:
            if not quiet: print("   ❌ No valid exit price, trying next expiration")
            continue

        # --- STOCK SPLIT LOGIC ---
        # If a split occurred, the value of the position is multiplied by the split ratio.
        # One contract became `split_ratio` new contracts.
        if split_info.get('has_split'):
            exit_price *= split_info['split_ratio']
            if not quiet:
                print(f"   💰 Split-adjusted exit value: ${exit_price:.2f} (original price * {split_info['split_ratio']})")
        
        entry_greeks_data = get_bulk_eod_greeks(symbol, exp_date, entry_date, quiet=quiet)
        api_call_count += 1
        entry_greeks = extract_greeks_from_bulk(entry_greeks_data, original_strike)
        exit_greeks_data = get_bulk_eod_greeks(symbol, exp_date, exit_date, quiet=quiet)
        api_call_count += 1
        exit_greeks = extract_greeks_from_bulk(exit_greeks_data, exit_strike)
        
        pnl_per_contract = exit_price - entry_price
        pnl_percentage = (pnl_per_contract / entry_price) * 100 if entry_price > 0 else 0
        
        if not quiet:
            print(f"🎉 OPTIMAL LEAPS FOUND!")
            print(f"   API calls used: {api_call_count}")
            print(f"   Entry: ${entry_price:.2f} (precise 10:00 AM)")
            print(f"   Exit: ${exit_price:.2f}")
            print(f"   P&L: ${pnl_per_contract:.2f} ({pnl_percentage:+.1f}%)")
        return {'expiration': exp_date, 'months_to_exp': months_out, 'original_strike': original_strike, 'exit_strike': exit_strike, 'entry_price': entry_price, 'exit_price': exit_price, 'pnl_per_contract': pnl_per_contract, 'return_pct': pnl_percentage, 'split_info': split_info, 'optimization_level': 'accurate_optimized', 'api_calls_used': api_call_count, 'expiration_tested': exp_date, 'total_expirations_available': len(january_exps), 'entry_greeks': entry_greeks, 'exit_greeks': exit_greeks}
    if not quiet:
        print(f"❌ No valid January LEAPS found after testing all {len(january_exps)} expirations")
        print(f"   Total API calls used: {api_call_count}")
    return None

def analyze_year_annual_january(year: int, quiet: bool = False) -> Optional[Dict[str, Any]]:
    if not quiet:
        print(f"\n📊 ANNUAL JANUARY ANALYSIS: {year}")
        print("="*80)
    entry_date = get_first_trading_day_of_year("GOOG", year)
    current_year = datetime.now().year
    if year == current_year:
        exit_date = get_most_recent_trading_day("GOOG")
        if not quiet: print(f"📅 Using most recent trading day for current year: {exit_date}")
    else:
        exit_date = get_last_trading_day_of_year("GOOG", year)
    if not entry_date or not exit_date: return None
    if not quiet:
        print(f"Entry: {entry_date}")
        print(f"Exit: {exit_date}")
    stock_price = get_stock_price_with_smart_fallback("GOOG", entry_date)
    if not stock_price: return None
    if not quiet: print(f"Stock price: ${stock_price:.2f}")
    start_time = time.time()
    result = find_optimal_leaps_annual_january("GOOG", year, entry_date, exit_date, stock_price, quiet=quiet)
    analysis_time = time.time() - start_time
    if not result:
        if not quiet: print(f"⏱️  Analysis time: {analysis_time:.2f} seconds")
        return None
    result.update({'year': year, 'analysis_time': analysis_time, 'entry_date': entry_date, 'exit_date': exit_date, 'stock_price_entry': stock_price})
    if not quiet: print(f"✅ SUCCESS - Analysis time: {analysis_time:.2f} seconds")
    return result

def execute_single_quarterly_trade(symbol: str, entry_date: str, exit_date: str, stock_price: float, fixed_strike: Optional[float] = None, quiet: bool = False) -> Optional[Dict[str, Any]]:
    if not quiet: print(f"\n🔄 Quarterly Trade: {entry_date} → {exit_date}")
    entry_dt = datetime.strptime(entry_date, '%Y%m%d').date()
    target_15_months = entry_dt + relativedelta(months=15)
    one_year_later = entry_dt + timedelta(days=365)
    if not quiet:
        print(f"📅 Entry Date: {entry_dt}")
        print(f"📅 Target 15-month date: {target_15_months}")
    all_available_expirations = get_expirations_available_on_date(symbol, entry_date, quiet=quiet)
    if not all_available_expirations:
        if not quiet: print("❌ No expirations found for entry date")
        return None
    leaps_expirations = [exp for exp in all_available_expirations if exp >= one_year_later]
    if not leaps_expirations:
        if not quiet: print("❌ No LEAPS-qualifying expirations found (≥1 year)")
        return None
    if not quiet: print(f"✅ Found {len(leaps_expirations)} LEAPS-qualifying expirations")
    closest_expiration_obj = find_closest_expiration_date(leaps_expirations, target_15_months)
    if not closest_expiration_obj:
        if not quiet: print("❌ No suitable expiration found")
        return None
    exp_date = closest_expiration_obj.strftime('%Y%m%d')
    months_out = (closest_expiration_obj - entry_dt).days / 30.4375
    deviation_days = abs((closest_expiration_obj - target_15_months).days)
    if not quiet: print(f"✅ Selected expiration: {exp_date} ({months_out:.1f} months, ±{deviation_days} days from target)")
    split_info = detect_stock_split(symbol, entry_date, exit_date)
    if not quiet and split_info.get('has_split'):
        print(f"📊 {split_info['description']} detected")
    entry_bulk_eod = get_bulk_eod_data(symbol, exp_date, entry_date, entry_date, quiet=quiet)
    if not entry_bulk_eod:
        if not quiet: print("❌ No entry EOD data available")
        return None
    valid_itm_calls = filter_itm_calls_from_bulk(entry_bulk_eod, stock_price, quiet=quiet)
    if not valid_itm_calls:
        if not quiet: print("❌ No valid ITM calls found")
        return None
    if fixed_strike:
        optimal_call = next((c for c in valid_itm_calls if c['strike'] == fixed_strike), None)
        if not optimal_call:
            if not quiet: print(f"❌ Fixed strike ${fixed_strike/1000:.2f} not available")
            return None
    else:
        optimal_call = valid_itm_calls[0]
    original_strike = optimal_call['strike']
    if not quiet: print(f"✅ Selected strike: ${original_strike/1000:.2f}")
    entry_quotes = get_bulk_at_time_quotes(symbol, exp_date, entry_date, ENTRY_TIME_MS, quiet=quiet)
    entry_price = extract_precise_entry_price_from_bulk(entry_quotes, original_strike, quiet=quiet)
    if not entry_price or entry_price <= 0:
        if not quiet: print("❌ No valid entry price available")
        return None
    exit_strike = original_strike
    if split_info.get('has_split'):
        exit_strike = original_strike // split_info['split_ratio']
        if not quiet: print(f"   🔄 Split adjustment: ${original_strike/1000:.2f} → ${exit_strike/1000:.2f}")
    exit_price = get_exit_price_individual(symbol, exp_date, exit_strike, exit_date, quiet=quiet)
    if exit_price is None or exit_price < 0:
        if not quiet: print("❌ No valid exit price available")
        return None

    # --- STOCK SPLIT LOGIC ---
    if split_info.get('has_split'):
        exit_price *= split_info['split_ratio']
        if not quiet:
            print(f"   💰 Split-adjusted exit value: ${exit_price:.2f} (original price * {split_info['split_ratio']})")

    entry_greeks_data = get_bulk_eod_greeks(symbol, exp_date, entry_date, quiet=quiet)
    entry_greeks = extract_greeks_from_bulk(entry_greeks_data, original_strike)
    exit_greeks_data = get_bulk_eod_greeks(symbol, exp_date, exit_date, quiet=quiet)
    exit_greeks = extract_greeks_from_bulk(exit_greeks_data, exit_strike)
    
    pnl_per_contract = exit_price - entry_price
    pnl_percentage = (pnl_per_contract / entry_price) * 100 if entry_price > 0 else 0
    
    entry_dt_datetime = datetime.strptime(entry_date, '%Y%m%d')
    exit_dt = datetime.strptime(exit_date, '%Y%m%d')
    hold_days = (exit_dt - entry_dt_datetime).days
    
    if not quiet:
        print(f"✅ Quarterly trade completed:")
        print(f"   Entry: ${entry_price:.2f} → Exit: ${exit_price:.2f}")
        print(f"   P&L: ${pnl_per_contract:.2f} ({pnl_percentage:+.1f}%)")
        print(f"   Hold period: {hold_days} days")
    return {'entry_date': entry_date, 'exit_date': exit_date, 'expiration': exp_date, 'months_to_exp': months_out, 'original_strike': original_strike, 'exit_strike': exit_strike, 'strike': original_strike, 'entry_price': entry_price, 'exit_price': exit_price, 'pnl_per_contract': pnl_per_contract, 'return_pct': pnl_percentage, 'hold_days': hold_days, 'split_info': split_info, 'target_15_months': target_15_months.strftime('%Y%m%d'), 'deviation_days': deviation_days, 'entry_greeks': entry_greeks, 'exit_greeks': exit_greeks}

def analyze_quarterly_strategy(symbol: str, year: int, use_fixed_strikes: bool = False, quiet: bool = False) -> Optional[Dict[str, Any]]:
    if not quiet:
        print(f"\n🔄 QUARTERLY ROLLING LEAPS ANALYSIS: {year}")
        print("="*80)
    q1_start = get_first_trading_day_of_year(symbol, year)
    q1_end = get_last_trading_day_of_quarter(symbol, year, 1)
    q2_end = get_last_trading_day_of_quarter(symbol, year, 2)
    q3_end = get_last_trading_day_of_quarter(symbol, year, 3)
    q4_end = get_last_trading_day_of_quarter(symbol, year, 4)
    current_year = datetime.now().year
    if year == current_year:
        year_end = get_most_recent_trading_day(symbol)
        if not quiet: print(f"📅 Using most recent trading day for current year: {year_end}")
        q4_end = year_end
    trade_schedule = [{'quarter': 'Q1', 'entry': q1_start, 'exit': q1_end}, {'quarter': 'Q2', 'entry': q1_end, 'exit': q2_end}, {'quarter': 'Q3', 'entry': q2_end, 'exit': q3_end}, {'quarter': 'Q4', 'entry': q3_end, 'exit': q4_end}]
    if not quiet:
        print("Quarterly Trading Schedule:")
        for item in trade_schedule:
            print(f"  {item['quarter']}: {item['entry']} → {item['exit']}")
    if not all([q1_start, q1_end, q2_end, q3_end]):
        if not quiet: print("❌ Could not get minimum required trading days (Q1-Q3)")
        return None
    trades = []
    yearly_pnl = 0.0
    fixed_strike = None
    for trade_info in trade_schedule:
        entry = trade_info['entry']
        exit_ = trade_info['exit']
        if not entry or not exit_: continue
        if not quiet: print(f"\n📊 {trade_info['quarter']} Position ({entry} → {exit_}):")
        stock_price = get_stock_price_with_smart_fallback(symbol, entry)
        if stock_price:
            trade_result = execute_single_quarterly_trade(symbol, entry, exit_, stock_price, fixed_strike, quiet=quiet)
            if trade_result:
                trades.append({**trade_result, 'quarter': trade_info['quarter']})
                yearly_pnl += trade_result['pnl_per_contract']
                if use_fixed_strikes and fixed_strike is None:
                    fixed_strike = trade_result['strike']
                    if not quiet: print(f"🔒 Fixed strike set for year: ${fixed_strike/1000:.2f}")
    if not trades: return None
    winning_trades = sum(1 for trade in trades if trade['pnl_per_contract'] > 0)
    total_investment = sum(trade['entry_price'] for trade in trades)
    yearly_return_pct = (yearly_pnl / total_investment) * 100 if total_investment > 0 else 0
    avg_hold_days = sum(trade['hold_days'] for trade in trades) / len(trades)
    months_list = [trade['months_to_exp'] for trade in trades]
    deviations = [trade.get('deviation_days', 0) for trade in trades]
    avg_months = sum(months_list) / len(months_list)
    max_deviation = max(deviations) if deviations else 0
    entry_deltas = [t['entry_greeks']['delta'] for t in trades if t.get('entry_greeks') and t['entry_greeks']]
    exit_deltas = [t['exit_greeks']['delta'] for t in trades if t.get('exit_greeks') and t['exit_greeks']]
    entry_ivs = [t['entry_greeks']['iv'] for t in trades if t.get('entry_greeks') and t['entry_greeks']]
    exit_ivs = [t['exit_greeks']['iv'] for t in trades if t.get('exit_greeks') and t['exit_greeks']]
    avg_entry_delta = sum(entry_deltas) / len(entry_deltas) if entry_deltas else 0
    avg_exit_delta = sum(exit_deltas) / len(exit_deltas) if exit_deltas else 0
    avg_entry_iv = sum(entry_ivs) / len(entry_ivs) if entry_ivs else 0
    avg_exit_iv = sum(exit_ivs) / len(exit_ivs) if exit_ivs else 0
    if not quiet:
        print(f"\n📈 15-Month Targeting Analysis:")
        print(f"   Average months to expiration: {avg_months:.1f}")
        print(f"   Max deviation from 15M target: {max_deviation} days")
    return {'year': year, 'strategy': 'quarterly_rolling_leaps_15month', 'trades': trades, 'yearly_summary': {'total_trades': len(trades), 'winning_trades': winning_trades, 'total_pnl': yearly_pnl, 'total_investment': total_investment, 'yearly_return_pct': yearly_return_pct, 'avg_hold_days': avg_hold_days, 'avg_months_to_exp': avg_months, 'max_deviation_days': max_deviation, 'avg_entry_delta': avg_entry_delta, 'avg_exit_delta': avg_exit_delta, 'avg_entry_iv': avg_entry_iv, 'avg_exit_iv': avg_exit_iv}, 'use_fixed_strikes': use_fixed_strikes, 'quarter_schedule': {'q1_period': f"{q1_start} → {q1_end}", 'q2_period': f"{q1_end} → {q2_end}", 'q3_period': f"{q2_end} → {q3_end}", 'q4_period': f"{q3_end} → {q4_end}"}}

def display_comparison_results(annual_results: List[Dict], quarterly_results: List[Dict]) -> None:
    print(f"\n\n🆚 STRATEGY DEEP DIVE: ANNUAL vs. QUARTERLY ROLLING LEAPS")
    print("=" * 120)
    print("This analysis compares the simple Annual-Hold strategy against the Quarterly Rolling strategy.")
    print("Greeks (Delta, IV) are shown at the point of entry and exit to reveal how each strategy performs under different market conditions.")
    print("-" * 120)
    header = (f"{'Year':<6} | {'Strategy':<11} | {'Return':>8} | {'Entry Δ':>8} | {'Exit Δ':>8} | {'Entry IV':>8} | {'Exit IV':>8} | {'Trades':>7} | {'Win Rate':>9}")
    print(header)
    print("-" * 120)
    all_years = sorted(list(set([r['year'] for r in annual_results] + [r['year'] for r in quarterly_results])))
    for year in all_years:
        annual_data = next((r for r in annual_results if r['year'] == year), None)
        if annual_data:
            entry_greeks = annual_data.get('entry_greeks') or {}
            exit_greeks = annual_data.get('exit_greeks') or {}
            annual_str = (f"{year:<6} | {'Annual':<11} | {annual_data.get('return_pct', 0):>7.1f}% | {entry_greeks.get('delta', 0):>8.2f} | {exit_greeks.get('delta', 0):>8.2f} | {entry_greeks.get('iv', 0):>8.3f} | {exit_greeks.get('iv', 0):>8.3f} | {'1':>7} | {'100.0%' if annual_data.get('return_pct', 0) > 0 else '0.0%' :>9}")
            print(annual_str)
        quarterly_data = next((r for r in quarterly_results if r['year'] == year), None)
        if quarterly_data:
            summary = quarterly_data['yearly_summary']
            win_rate = (summary['winning_trades'] / summary['total_trades']) * 100 if summary['total_trades'] > 0 else 0
            quarterly_str = (f"{'':<6} | {'Quarterly':<11} | {summary.get('yearly_return_pct', 0):>7.1f}% | {summary.get('avg_entry_delta', 0):>8.2f} | {summary.get('avg_exit_delta', 0):>8.2f} | {summary.get('avg_entry_iv', 0):>8.3f} | {summary.get('avg_exit_iv', 0):>8.3f} | {summary['total_trades']:>7} | {win_rate:>8.1f}% ")
            print(quarterly_str)
        print("-" * 120)
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
    parser = argparse.ArgumentParser(description='LEAPS Strategy Backtesting')
    parser.add_argument('--strategy', choices=['annual', 'quarterly', 'both'], default='both', help='Strategy to test (default: both)')
    parser.add_argument('--use-fixed-strikes', action='store_true', help='Use the same strike price for all quarterly trades within a single year')
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
                print(f"{r['year']}: {r.get('return_pct', 0):+.1f}% (API calls: {r.get('api_calls_used', 0)})")
    if args.strategy in ['quarterly', 'both']:
        print("\n🔄 QUARTERLY ROLLING 15-MONTH LEAPS STRATEGY")
        print("📊 Buy a ~15-month LEAP and roll it at the end of each quarter.")
        print("-" * 80)
        for year in years:
            result = analyze_quarterly_strategy("GOOG", year, args.use_fixed_strikes)
            if result:
                quarterly_results.append(result)
                summary = result['yearly_summary']
                print(f"\n{year} Quarterly Results:")
                print(f"   Total Return: {summary['yearly_return_pct']:+.1f}%")
                print(f"   Trades: {summary['total_trades']} (Wins: {summary['winning_trades']})")
                print(f"   Average Hold: {summary['avg_hold_days']:.0f} days")
                for trade in result['trades']:
                    print(f"   {trade['quarter']}: {trade['return_pct']:+.1f}% ({trade['hold_days']} days)")
    if args.strategy == 'both' and annual_results and quarterly_results:
        display_comparison_results(annual_results, quarterly_results)
    print(f"\n✅ BACKTESTING COMPLETE")
    print(f"📊 Strategy: {args.strategy.title()}")
    if args.use_fixed_strikes and args.strategy in ['quarterly', 'both']:
        print(f"🔒 Fixed strikes: Enabled")
    print("=" * 80)

if __name__ == "__main__":
    main()
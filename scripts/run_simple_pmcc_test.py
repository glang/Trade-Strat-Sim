#!/usr/bin/env python3
"""
Simple Poor Man's Covered Call (PMCC) Test Script

This script is a focused test to validate the core mechanics of a PMCC strategy
for a single year and a single short call transaction. It will:
1.  Buy a deep ITM LEAPS call at the start of the year.
2.  Sell a single, ~35 DTE, ~0.30 delta call against it on the same day.
3.  Calculate the P&L for both legs of the trade.
4.  Present a clear report comparing the simple buy-and-hold LEAPS strategy
    to the PMCC strategy.
"""

import argparse
import sys
import os
import httpx
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional, Any

# --- Path setup ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# --- Import existing functions ---
from src.backtesting_engine.theta_connection_manager import ensure_theta_terminal_connected
from src.backtesting_engine.accurate_optimized_leaps import (
    get_expirations_available_on_date,
    get_bulk_eod_greeks,
    get_exit_price_individual,
    find_optimal_leaps_annual_january,
    api_call,
    api_call_csv,
    format_date_for_api
)
from src.backtesting_engine.market_days_cache import get_first_trading_day_of_year
from src.backtesting_engine.smart_leaps_backtest import get_stock_price_with_smart_fallback

# --- Constants ---
SYMBOL = "GOOG"
TARGET_DTE = 35
TARGET_DELTA = 0.30
MIN_VOLUME = 5  # Increased minimum volume requirement
MIN_OPEN_INTEREST = 0  # Disable open interest requirement since historical OI data isn't available

def get_historical_open_interest(
    symbol: str,
    exp_date: str,
    strike: int,
    date: str,
    quiet: bool = False
) -> Optional[int]:
    """
    Fetches the historical open interest for a single contract on a specific date.
    """
    # Use CSV API call format with proper date conversion
    url = "http://localhost:25503/v3/option/history/open_interest"
    exp_formatted = format_date_for_api(exp_date)
    date_formatted = format_date_for_api(date)
    
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "strike": strike,
        "right": "call",
        "date": date_formatted
    }
    response = api_call_csv(url, params, quiet=True)
    if response and len(response) > 1:  # Check we have more than just header
        # Skip header row and get first data row
        data_row = response[1]
        if len(data_row) >= 2:
            return int(data_row[1])  # Open interest is in column 1
    return None


def find_and_price_short_call(
    symbol: str,
    trade_date: str,
    stock_price: float,
    quiet: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Finds and prices a single, liquid, OTM short-term call option.
    """
    if not quiet:
        print("\n" + "-"*50)
        print("🔎 Finding best short call candidate...")
        print(f"   Trade Date: {trade_date}, Stock Price: ${stock_price:.2f}")

    # 1. Determine the theoretical target expiration date
    trade_dt = datetime.strptime(trade_date, '%Y%m%d').date()
    target_expiration_date = trade_dt + relativedelta(days=TARGET_DTE)
    if not quiet: print(f"   - Theoretical Target Expiration: {target_expiration_date}")

    # 2. Find the best *available* expiration date
    available_expirations = get_expirations_available_on_date(symbol, trade_date, quiet=True)
    if not available_expirations:
        if not quiet: print("   - ❌ No available expirations found.")
        return None
    
    actual_expiration_date = min(available_expirations, key=lambda d: abs(d - target_expiration_date))
    actual_expiration_str = actual_expiration_date.strftime('%Y%m%d')
    if not quiet: print(f"   - Best Available Expiration: {actual_expiration_str}")

    # 3. Get all potential OTM call candidates from the Greeks endpoint
    # Use CSV API call format with proper date conversion
    url = "http://localhost:25503/v3/option/history/greeks/eod"
    exp_formatted = format_date_for_api(actual_expiration_str)
    date_formatted = format_date_for_api(trade_date)
    
    params = {
        "symbol": symbol,
        "expiration": exp_formatted,
        "start_date": date_formatted,
        "end_date": date_formatted
    }
    response = api_call_csv(url, params, quiet=True)

    if not response or len(response) <= 1:
        if not quiet: print(f"   - ❌ Could not fetch Greeks for {actual_expiration_str}.")
        return None

    otm_candidates = []
    stock_price_dollars = stock_price  # Keep in dollars for comparison
    
    # Skip header row
    for row in response[1:]:
        try:
            if len(row) < 19: continue
            # Parse CSV fields based on Greeks EOD format
            # Columns: symbol,expiration,strike,right,created,last_trade,open,high,low,close,volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition
            strike = float(row[2])  # Strike in dollars
            right = row[3]  # Option type
            volume = int(row[10]) if row[10] else 0  # Volume
            
            if right != 'CALL' or strike <= stock_price_dollars:
                continue
            
            # For Greeks, we need to get the delta from the Greeks-specific endpoint
            # For now, let's use a simplified approach and get delta from a separate call
            # We'll approximate delta based on moneyness for initial filtering
            moneyness = strike / stock_price_dollars
            approximate_delta = max(0.1, 1.0 - (moneyness - 1.0) * 2)  # Rough approximation
            
            # Skip open interest fetch since historical OI data isn't available
            strike_milli = int(strike * 1000)  # Convert to millidollars for consistency
            
            otm_candidates.append({
                'strike': strike_milli,  # Keep in millidollars for consistency
                'delta': approximate_delta,
                'volume': volume,
                'open_interest': 0  # Set to 0 since historical OI data isn't available
            })
        except (ValueError, IndexError, TypeError):
            continue
    
    if not otm_candidates:
        if not quiet: print(f"   - ❌ No valid OTM calls found for {actual_expiration_str}.")
        return None

    # 4. Select the single best candidate using Delta and Liquidity
    otm_candidates.sort(key=lambda x: abs(x['delta'] - TARGET_DELTA))
    
    if not quiet:
        print("   --- Checking OTM Candidates (sorted by delta proximity) ---")
        for cand in otm_candidates:
            print(f"     - Strike: ${cand['strike']/1000:<8.2f} Delta: {cand['delta']:<6.2f} Volume: {cand['volume']:<5} OI: {cand['open_interest']:<5}")

    final_selection = None
    for candidate in otm_candidates:
        if candidate['volume'] >= MIN_VOLUME and candidate['open_interest'] >= MIN_OPEN_INTEREST:
            final_selection = candidate
            break

    
    if not final_selection:
        if not quiet: print("   - ❌ No liquid candidates found after checking all OTM calls.")
        return None
        
    if not quiet:
        print(f"   - ✅ Selected Candidate: Strike ${final_selection['strike']/1000:.2f}, Delta {final_selection['delta']:.2f}")

    # 5. Get the final price (premium) for the selected candidate
    premium_collected = get_exit_price_individual(symbol, actual_expiration_str, final_selection['strike'], trade_date, quiet=True)
    if premium_collected is None or premium_collected <= 0:
        if not quiet: print(f"   - ❌ Could not get a valid premium for the selected strike.")
        return None

    # 6. Get the price at expiration to calculate P&L
    cost_to_close = get_exit_price_individual(symbol, actual_expiration_str, final_selection['strike'], actual_expiration_str, quiet=True)
    if cost_to_close is None:
        if not quiet: print(f"   - ❌ Could not get a valid closing price for the short call.")
        return None

    final_selection['expiration_date'] = actual_expiration_str
    final_selection['premium_collected'] = premium_collected
    final_selection['cost_to_close'] = cost_to_close
    final_selection['pnl'] = premium_collected - cost_to_close

    return final_selection


def main():
    """ Main execution function """
    parser = argparse.ArgumentParser(description="Simple PMCC Strategy Test")
    parser.add_argument('--year', type=int, default=2023, help='Year to test')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    args = parser.parse_args()

    if not ensure_theta_terminal_connected(quiet=args.quiet):
        print("❌ Critical Error: Could not connect to ThetaTerminal. Aborting.")
        sys.exit(1)

    print("="*80)
    print(f"🎯 Running Simple PMCC Test for {args.year}")
    print("="*80)

    # --- Get Trade Dates and Prices ---
    trade_date = get_first_trading_day_of_year(SYMBOL, args.year, quiet=True)
    if not trade_date:
        print(f"❌ Could not determine the first trading day for {args.year}.")
        sys.exit(1)

    stock_price = get_stock_price_with_smart_fallback(SYMBOL, trade_date, quiet=True)
    if not stock_price:
        print(f"❌ Could not get stock price for {trade_date}.")
        sys.exit(1)

    # --- 1. Analyze the Long LEAPS Leg ---
    print("--- Analyzing Long LEAPS Leg ---")
    
    # The exit date for the LEAPS is the last trading day of the year.
    from src.backtesting_engine.market_days_cache import get_last_trading_day_of_year
    leaps_exit_date = get_last_trading_day_of_year(SYMBOL, args.year, quiet=True)
    if not leaps_exit_date:
        print(f"❌ Could not determine the last trading day for {args.year}.")
        sys.exit(1)

    long_leaps_result = find_optimal_leaps_annual_january(
        SYMBOL, args.year, trade_date, leaps_exit_date, stock_price, quiet=args.quiet
    )

    if not long_leaps_result or 'entry_price' not in long_leaps_result or 'exit_price' not in long_leaps_result:
        print("❌ Failed to find a valid long LEAPS call or get its full price data.")
        sys.exit(1)
    
    long_leaps_pnl = (long_leaps_result['exit_price'] - long_leaps_result['entry_price']) * 100
    long_leaps_exit_price = long_leaps_result['exit_price']

    # --- 2. Analyze the Short Call Leg ---
    short_call_result = find_and_price_short_call(SYMBOL, trade_date, stock_price, quiet=args.quiet)

    # --- 3. Display Final Report ---
    print("\n\n" + "="*80)
    print(f"📈 FINAL RESULTS FOR {args.year}")
    print("="*80)

    print(f"--- Long LEAPS Leg (Buy and Hold) ---")
    print(f"  - Contract: {SYMBOL} {long_leaps_result['expiration']} ${long_leaps_result['original_strike']/1000:.2f} Call")
    print(f"  - Entry Price: ${long_leaps_result['entry_price']:.2f}")
    print(f"  - Exit Price:  ${long_leaps_exit_price:.2f}")
    print(f"  - P&L per Contract: ${long_leaps_pnl/100:,.2f}")

    if not short_call_result:
        print("\n--- Short Call Leg ---")
        print("  - ❌ Failed to find a suitable short call to sell.")
    else:
        print("\n--- Short Call Leg ---")
        print(f"  - Contract: {SYMBOL} {short_call_result['expiration_date']} ${short_call_result['strike']/1000:.2f} Call")
        print(f"  - Premium Collected: ${short_call_result['premium_collected']:.2f}")
        print(f"  - Cost to Close:     ${short_call_result['cost_to_close']:.2f}")
        print(f"  - P&L per Contract:  ${short_call_result['pnl']:.2f}")

    print("\n" + "-"*80)
    print("--- Strategy Comparison (per contract) ---")
    if short_call_result:
        pmcc_pnl = long_leaps_pnl/100 + short_call_result['pnl']
        print(f"  - Buy and Hold LEAPS P&L: ${long_leaps_pnl/100:,.2f}")
        print(f"  - PMCC Strategy P&L:      ${pmcc_pnl:,.2f}")
        print(f"  - Income from Short Call: ${short_call_result['pnl']:,.2f}")
    else:
        print("  - Could not calculate PMCC performance due to missing short call.")
    print("="*80)


if __name__ == "__main__":
    main()

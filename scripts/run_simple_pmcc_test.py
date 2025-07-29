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
    api_call
)
from src.backtesting_engine.market_days_cache import get_first_trading_day_of_year
from src.backtesting_engine.smart_leaps_backtest import get_stock_price_with_smart_fallback

# --- Constants ---
SYMBOL = "GOOG"
TARGET_DTE = 35
TARGET_DELTA = 0.30
MIN_VOLUME = 1
MIN_OPEN_INTEREST = 10

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
    cmd = f'curl -s "http://127.0.0.1:25510/v2/hist/option/open_interest?root={symbol}&exp={exp_date}&strike={strike}&right=C&start_date={date}&end_date={date}"'
    data = api_call(cmd, quiet=True)
    if data and 'response' in data and data['response']:
        # Response format: [["ms_of_day", "open_interest", "date"]]
        tick = data['response'][0]
        if len(tick) >= 2:
            return tick[1]
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
    cmd = f'curl -s "http://127.0.0.1:25510/v2/bulk_hist/option/eod_greeks?root={symbol}&exp={actual_expiration_str}&start_date={trade_date}&end_date={trade_date}"'
    bulk_greeks_data = api_call(cmd, quiet=True)

    if not bulk_greeks_data or 'response' not in bulk_greeks_data:
        if not quiet: print(f"   - ❌ Could not fetch Greeks for {actual_expiration_str}.")
        return None

    otm_candidates = []
    stock_price_milli = stock_price * 1000
    for contract_data in bulk_greeks_data['response']:
        try:
            contract = contract_data.get('contract', {})
            if contract.get('right') != 'C' or contract.get('strike', 0) <= stock_price_milli:
                continue
            
            tick = contract_data.get('ticks', [[]])[0]
            if len(tick) >= 16: # Delta is at index 15, Volume is at index 5
                # Fetch open interest for this specific contract
                open_interest = get_historical_open_interest(symbol, actual_expiration_str, contract['strike'], trade_date, quiet=True)
                
                otm_candidates.append({
                    'strike': contract['strike'],
                    'delta': tick[15],
                    'volume': tick[5],
                    'open_interest': open_interest if open_interest is not None else 0
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

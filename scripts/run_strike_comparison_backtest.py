#!/usr/bin/env python3
"""
Strike-Selection Strategy Comparison Backtester

This script backtests and compares three different strike-selection strategies
for an annual LEAPS (Long-term Equity Anticipation Securities) holding strategy:

1.  **Barely ITM (In-The-Money):** Selects the strike that is closest to, but
    still below, the current stock price. This is the classic approach.

2.  **Most OTM (Out-of-The-Money):** Selects the call option with the absolute
    highest available strike price for a given expiration. This is a high-risk,
    high-reward approach.

3.  **Mid-Point:** Calculates the average between the "Barely ITM" and "Most OTM"
    strikes and selects the tradable strike closest to that average. This is
    a balanced approach.

The goal is to analyze how the choice of strike price impacts the performance
of the annual LEAPS strategy under different market conditions.
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

# --- Path setup ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# --- Import existing functions ---
from src.backtesting_engine.theta_connection_manager import ensure_theta_terminal_connected
from src.backtesting_engine.accurate_optimized_leaps import (
    get_january_expirations,
    get_bulk_eod_data,
    get_bulk_at_time_quotes,
    extract_precise_entry_price_from_bulk,
    get_exit_price_individual,
    detect_stock_split,
    ENTRY_TIME_MS
)
from src.backtesting_engine.market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_most_recent_trading_day
)
from src.backtesting_engine.smart_leaps_backtest import get_stock_price_with_smart_fallback
from src.backtesting_engine.capital_management import calculate_position_size, calculate_exit_proceeds

# --- Constants ---
SYMBOL = "GOOG"
STARTING_CAPITAL = 100000.0

def get_all_available_calls(bulk_data: Dict[str, Any], quiet: bool = False) -> List[Dict[str, Any]]:
    """
    Parses bulk EOD data to get a list of all available call options.

    Args:
        bulk_data: The raw bulk EOD data from the ThetaData API.
        quiet: If True, suppress verbose output.

    Returns:
        A list of dictionaries, each representing a valid call option.
    """
    if not bulk_data or 'response' not in bulk_data:
        return []

    valid_calls = []
    for contract_data in bulk_data['response']:
        try:
            contract = contract_data.get('contract', {})
            ticks = contract_data.get('ticks', [])
            if not ticks or not contract:
                continue

            strike = contract.get('strike', 0)
            right = contract.get('right', '')
            if right != 'C':
                continue

            tick = ticks[0]
            if len(tick) < 8:  # Ensure there's enough data for volume
                continue

            # From documentation: ["ms_of_day", ..., "close", "volume", ...]
            # Index 5 is 'close', Index 6 is 'volume'
            close_price = tick[5] if tick[5] is not None else 0
            volume = tick[6] if tick[6] is not None else 0
            bid = tick[10] if tick[10] is not None else 0
            ask = tick[14] if tick[14] is not None else 0

            # We need a valid price to consider the contract tradable
            if close_price > 0 or (bid > 0 and ask > 0):
                valid_calls.append({
                    'strike': strike,
                    'close': close_price,
                    'volume': volume,
                    'bid': bid,
                    'ask': ask
                })
        except (ValueError, IndexError, TypeError) as e:
            if not quiet:
                print(f"⚠️  Skipping contract due to parsing error: {e}")
            continue

    # Sort by strike price for predictable order
    valid_calls.sort(key=lambda x: x['strike'])
    if not quiet:
        print(f"✅ Found {len(valid_calls)} total available call contracts.")
    return valid_calls


def analyze_annual_strategy_variant(
    year: int,
    stock_price: float,
    entry_date: str,
    exit_date: str,
    strategy: str,
    quiet: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Analyzes a single year for a given strike-selection strategy variant.
    """
    if not quiet:
        print(f"\n" + "="*50)
        print(f"🔬 ANALYZING YEAR: {year} | STRATEGY: {strategy}")
        print(f"   Stock Price: ${stock_price:.2f} on {entry_date}")
        print(f"="*50)

    january_exps = get_january_expirations(SYMBOL, year, entry_date, quiet=True)
    if not january_exps:
        if not quiet: print(f"❌ No January {year+1} expirations found.")
        return {'error': f"No January {year+1} expirations."}

    # Test expirations until a valid trade can be found
    for exp_date in january_exps:
        if not quiet: print(f"➡️  Testing Expiration: {exp_date}")
        bulk_eod_data = get_bulk_eod_data(SYMBOL, exp_date, entry_date, entry_date, quiet=True)
        all_calls = get_all_available_calls(bulk_eod_data, quiet=True)

        if not all_calls:
            if not quiet: print("   ❌ No call options found for this expiration. Trying next.")
            continue

        # --- Strike Selection Logic ---
        selected_strike = None
        stock_price_milli = stock_price * 1000

        # 1. Find Barely ITM strike
        itm_calls = [c for c in all_calls if c['strike'] < stock_price_milli]
        if not itm_calls:
            if not quiet: print("   ❌ No ITM calls available. Trying next expiration.")
            continue
        barely_itm_strike = max(itm_calls, key=lambda x: x['strike'])

        # 2. Find Most OTM strike
        most_otm_strike = max(all_calls, key=lambda x: x['strike'])

        if strategy == 'ITM':
            selected_strike = barely_itm_strike
        elif strategy == 'OTM':
            selected_strike = most_otm_strike
        elif strategy == 'MID':
            mid_point = (barely_itm_strike['strike'] + most_otm_strike['strike']) / 2
            
            # Find the strike closest to the mid-point
            closest_strikes = sorted(all_calls, key=lambda x: abs(x['strike'] - mid_point))
            
            # Check for ties
            if len(closest_strikes) > 1 and abs(closest_strikes[0]['strike'] - mid_point) == abs(closest_strikes[1]['strike'] - mid_point):
                if not quiet: print(f"   - Tie detected between strikes {closest_strikes[0]['strike']/1000} and {closest_strikes[1]['strike']/1000}. Checking volume.")
                # Tie-breaking rule: highest volume
                if closest_strikes[0]['volume'] >= closest_strikes[1]['volume']:
                    selected_strike = closest_strikes[0]
                else:
                    selected_strike = closest_strikes[1]
            else:
                selected_strike = closest_strikes[0]
        
        if not selected_strike:
            if not quiet: print(f"   ❌ Could not determine strike for strategy '{strategy}'.")
            return {'error': f"Could not select strike for {strategy}."}

        if not quiet:
            print(f"   - Barely ITM Strike: ${barely_itm_strike['strike']/1000:.2f}")
            print(f"   - Most OTM Strike:   ${most_otm_strike['strike']/1000:.2f}")
            if strategy == 'MID':
                print(f"   - Mid-Point Target:  ${(barely_itm_strike['strike'] + most_otm_strike['strike'])/2000:.2f}")
            print(f"   ✅ Selected Strike for {strategy}: ${selected_strike['strike']/1000:.2f}")

        # --- Execute Trade with Selected Strike ---
        entry_quotes = get_bulk_at_time_quotes(SYMBOL, exp_date, entry_date, ENTRY_TIME_MS, quiet=True)
        entry_price = extract_precise_entry_price_from_bulk(entry_quotes, selected_strike['strike'], quiet=True)

        if not entry_price or entry_price <= 0:
            if not quiet: print(f"   ❌ No valid entry price for strike ${selected_strike['strike']/1000:.2f}. Trying next expiration.")
            continue

        split_info = detect_stock_split(SYMBOL, entry_date, exit_date)
        exit_strike = selected_strike['strike']
        if split_info.get('has_split'):
            exit_strike //= split_info['split_ratio']

        exit_price = get_exit_price_individual(SYMBOL, exp_date, exit_strike, exit_date, quiet=True)

        if exit_price is None:
            if not quiet: print(f"   ❌ No valid exit price for strike ${exit_strike/1000:.2f}. Trying next expiration.")
            continue
        
        if split_info.get('has_split'):
            exit_price *= split_info['split_ratio']

        # --- Calculate Results ---
        position_info = calculate_position_size(STARTING_CAPITAL, entry_price)
        if position_info['error']:
             return {'error': position_info['error']}
        
        exit_info = calculate_exit_proceeds(position_info['num_contracts'], exit_price)
        
        final_capital = exit_info['net_proceeds'] + position_info['leftover_cash']
        yearly_return_pct = ((final_capital - STARTING_CAPITAL) / STARTING_CAPITAL) * 100

        if not quiet:
            print(f"   - Entry Price: ${entry_price:.2f}")
            print(f"   - Exit Price:  ${exit_price:.2f}")
            print(f"   - Contracts:   {position_info['num_contracts']}")
            print(f"   - Return:      {yearly_return_pct:+.1f}%")

        return {
            'year': year,
            'strategy': strategy,
            'selected_strike': selected_strike['strike'] / 1000,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'final_capital': final_capital,
            'return_pct': yearly_return_pct,
            'error': None
        }

    if not quiet:
        print(f"❌ Could not find a valid trade for {year} using strategy {strategy} after testing all expirations.")
    return {'error': f"No valid trade found for {year} with {strategy}."}


def main():
    """ Main execution function """
    parser = argparse.ArgumentParser(description="Strike-Selection Strategy Comparison for LEAPS")
    parser.add_argument('--start-year', type=int, default=2016, help='Starting year for backtest')
    parser.add_argument('--end-year', type=int, default=datetime.now().year, help='Ending year for backtest')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    args = parser.parse_args()

    if not ensure_theta_terminal_connected(quiet=args.quiet):
        print("❌ Critical Error: Could not connect to ThetaTerminal. Aborting.")
        sys.exit(1)

    print("="*80)
    print("🎯 LEAPS Strike-Selection Strategy Comparison")
    print(f"📅 Running backtest from {args.start_year} to {args.end_year}")
    print("="*80)

    all_results = []
    strategies_to_test = ['ITM', 'OTM', 'MID']

    for year in range(args.start_year, args.end_year + 1):
        entry_date = get_first_trading_day_of_year(SYMBOL, year, quiet=True)
        exit_date = get_most_recent_trading_day(SYMBOL, quiet=True) if year == datetime.now().year else get_last_trading_day_of_year(SYMBOL, year, quiet=True)

        if not entry_date or not exit_date:
            print(f"Could not get trading dates for {year}. Skipping.")
            continue

        stock_price = get_stock_price_with_smart_fallback(SYMBOL, entry_date, quiet=True)
        if not stock_price:
            print(f"Could not get stock price for {year}. Skipping.")
            continue

        year_results = []
        for strategy in strategies_to_test:
            result = analyze_annual_strategy_variant(year, stock_price, entry_date, exit_date, strategy, quiet=args.quiet)
            if result:
                year_results.append(result)
        
        if year_results:
            all_results.extend(year_results)

    # --- Display Final Report ---
    print("\n\n" + "="*80)
    print("📈 FINAL RESULTS: Strike-Selection Strategy Comparison")
    print("="*80)
    print(f"{'Year':<7} | {'Strategy':<10} | {'Strike ($)':<12} | {'Return (%)':>12}")
    print("-" * 80)

    # Group results by year for clear comparison
    results_by_year = {}
    for res in all_results:
        if res.get('error'):
            continue
        year = res['year']
        if year not in results_by_year:
            results_by_year[year] = []
        results_by_year[year].append(res)

    for year in sorted(results_by_year.keys()):
        for result in sorted(results_by_year[year], key=lambda x: x['strategy']):
            print(
                f"{result['year']:<7} | "
                f"{result['strategy']:<10} | "
                f"{result['selected_strike']:<12.2f} | "
                f"{result['return_pct']:>12.1f}"
            )
        print("-" * 80)

if __name__ == "__main__":
    main()

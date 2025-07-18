#!/usr/bin/env python3
"""
ITM vs. OTM LEAPS Performance Test for a Bull Year (v2)

This script conducts a focused experiment to compare the performance of two
different option selection strategies within a single, strong bull market year.

This version has been updated to be more robust, iterating through all
available January expirations to find one with valid, liquid data for
both the ITM and OTM options, ensuring a fair head-to-head comparison.
"""

import argparse
import sys
import os
from math import floor
from typing import Dict, List, Any, Optional

# --- Path setup ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# --- Import required functions ---
from src.backtesting_engine.accurate_optimized_leaps import (
    ensure_theta_terminal_running,
    get_january_expirations,
    get_bulk_eod_data,
    get_bulk_at_time_quotes,
    extract_precise_entry_price_from_bulk,
    get_exit_price_individual,
    ENTRY_TIME_MS
)
from src.backtesting_engine.market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
)
from src.backtesting_engine.smart_leaps_backtest import get_stock_price_with_smart_fallback

# --- Test Configuration ---
TEST_YEAR = 2021
STARTING_CAPITAL = 100000.0
SYMBOL = "GOOG"
OTM_DOLLAR_AMOUNT = 10.0  # $10 OTM

def find_specific_leap(
    exp_date: str,
    stock_price: float,
    entry_date: str,
    strategy: str = 'ITM'
) -> Optional[Dict[str, Any]]:
    """
    Finds a specific LEAP option based on the strategy (ITM or OTM).
    """
    bulk_eod = get_bulk_eod_data(SYMBOL, exp_date, entry_date, entry_date, quiet=True)
    if not bulk_eod:
        return None

    all_calls = []
    for contract_data in bulk_eod.get('response', []):
        contract = contract_data.get('contract', {})
        if contract.get('right') == 'C':
            all_calls.append(contract)

    if not all_calls:
        return None

    if strategy == 'ITM':
        # Find ITM strike closest to stock price
        target_strike = stock_price * 1000
        best_option = min(
            (c for c in all_calls if c['strike'] < target_strike),
            key=lambda c: abs(c['strike'] - target_strike),
            default=None
        )
    elif strategy == 'OTM':
        # Find OTM strike at least $10 away
        target_strike = (stock_price + OTM_DOLLAR_AMOUNT) * 1000
        best_option = min(
            (c for c in all_calls if c['strike'] >= target_strike),
            key=lambda c: abs(c['strike'] - target_strike),
            default=None
        )
    else:
        return None

    return best_option

def get_trade_results(exp_date: str, option: Dict[str, Any], entry_date: str, exit_date: str) -> Optional[Dict[str, Any]]:
    """
    Gets prices and calculates P&L for a given option.
    """
    entry_quotes = get_bulk_at_time_quotes(SYMBOL, exp_date, entry_date, ENTRY_TIME_MS, quiet=True)
    entry_price = extract_precise_entry_price_from_bulk(entry_quotes, option['strike'], quiet=True)
    exit_price = get_exit_price_individual(SYMBOL, exp_date, option['strike'], exit_date, quiet=True)

    if not all([entry_price, exit_price]):
        return None
    
    num_contracts = floor(STARTING_CAPITAL / entry_price)
    total_cost = num_contracts * entry_price
    final_value = num_contracts * exit_price
    profit = final_value - total_cost
    return_pct = (profit / total_cost) * 100 if total_cost > 0 else 0

    return {
        "Strike": f"${option['strike']/1000.0:.2f}",
        "Entry Price": f"${entry_price:.2f}",
        "Exit Price": f"${exit_price:.2f}",
        "Contracts": num_contracts,
        "Profit": f"${profit:,.2f}",
        "Return": f"{return_pct:.2f}%"
    }

def main():
    print("🔬 ITM vs. OTM LEAPS Performance Test (v2)")
    print("=" * 80)
    print(f"YEAR: {TEST_YEAR} (Strong Bull Market)")
    print(f"CAPITAL PER STRATEGY: ${STARTING_CAPITAL:,.2f}")
    print("=" * 80)

    if not ensure_theta_terminal_running(quiet=True):
        print("❌ Critical Error: Could not connect to ThetaTerminal. Aborting.")
        return

    # --- Setup Dates and Prices ---
    entry_date = get_first_trading_day_of_year(SYMBOL, TEST_YEAR, quiet=True)
    exit_date = get_last_trading_day_of_year(SYMBOL, TEST_YEAR, quiet=True)
    stock_price_entry = get_stock_price_with_smart_fallback(SYMBOL, entry_date, quiet=True)

    if not all([entry_date, exit_date, stock_price_entry]):
        print("❌ Could not retrieve necessary market data for the test.")
        return

    print(f"Entry Date: {entry_date} | Exit Date: {exit_date}")
    print(f"GOOG Price at Entry: ${stock_price_entry:.2f}")
    print("-" * 80)

    # --- Find a suitable expiration and run tests ---
    jan_expirations = get_january_expirations(SYMBOL, TEST_YEAR, entry_date, quiet=True)
    if not jan_expirations:
        print("❌ No valid January LEAP expirations found for the test year.")
        return

    final_results = []
    for exp_date in jan_expirations:
        print(f"Testing Expiration: {exp_date}...")

        # Find options for both strategies
        itm_option = find_specific_leap(exp_date, stock_price_entry, entry_date, strategy='ITM')
        otm_option = find_specific_leap(exp_date, stock_price_entry, entry_date, strategy='OTM')

        if not itm_option or not otm_option:
            print("  Could not find valid ITM or OTM options for this expiration. Trying next...\n")
            continue

        # Get results for both
        itm_results = get_trade_results(exp_date, itm_option, entry_date, exit_date)
        otm_results = get_trade_results(exp_date, otm_option, entry_date, exit_date)

        if itm_results and otm_results:
            print("  ✅ Found valid data for both strategies!")
            final_results.append({"Strategy": "ITM", **itm_results})
            final_results.append({"Strategy": "OTM", **otm_results})
            break # Stop after the first successful expiration
        else:
            print("  Could not retrieve full pricing for both options. Trying next...\n")

    # --- Final Comparison ---
    print("\n" + "=" * 80)
    print("📊 FINAL RESULTS COMPARISON")
    print("=" * 80)
    if final_results:
        header = f"{'Strategy':<10} | {'Strike':<10} | {'Entry Price':<12} | {'Exit Price':<12} | {'Contracts':<10} | {'Profit':>15} | {'Return':>10}"
        print(header)
        print("-" * 80)
        for res in final_results:
            row = f"{res['Strategy']:<10} | {res['Strike']:<10} | {res['Entry Price']:<12} | {res['Exit Price']:<12} | {res['Contracts']:<10} | {res['Profit']:>15} | {res['Return']:>10}"
            print(row)
    else:
        print("No valid trades could be executed for any January expiration.")
    print("=" * 80)

if __name__ == "__main__":
    main()
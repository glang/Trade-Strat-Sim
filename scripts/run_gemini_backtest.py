#!/usr/bin/env python3
"""
Gemini's Implementation of a Compounding LEAPS Backtester (v8 - Corrected)

This script implements and backtests two LEAPS (Long-term Equity
AnticiPation Securities) strategies using a capital management model.
It simulates how a portfolio would grow by reinvesting proceeds from
trades throughout the year.

This version has all logging permanently enabled and correctly handles
stock splits by adjusting the stock price for option selection and applying
the correct contract multiplier.
"""

import argparse
import sys
import os
from math import floor
from datetime import datetime
from typing import Dict, List, Any, Optional

# --- Path setup to allow importing from the backtesting_engine package ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# --- Reuse existing, tested functions from the project ---
from src.backtesting_engine.accurate_optimized_leaps import (
    ensure_theta_terminal_running,
    find_optimal_leaps_annual_january,
    execute_single_quarterly_trade,
    detect_stock_split
)
from src.backtesting_engine.market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_most_recent_trading_day,
    get_last_trading_day_of_quarter
)
from src.backtesting_engine.smart_leaps_backtest import get_stock_price_with_smart_fallback

# --- Main Analysis Functions ---

COMMISSION_PER_CONTRACT = 0.35

def analyze_year_compounding_annual(year: int, starting_capital: float) -> Optional[Dict[str, Any]]:
    """
    Analyzes the Compounding Annual Strategy for a single year.
    """
    print(f"\n📈 COMPOUNDING ANNUAL ANALYSIS: {year}")
    print("-" * 80)

    entry_date = get_first_trading_day_of_year("GOOG", year)
    exit_date = get_most_recent_trading_day("GOOG") if year == datetime.now().year else get_last_trading_day_of_year("GOOG", year)
    if not entry_date or not exit_date:
        print(f"❌ Could not determine trading dates for {year}.")
        return None

    stock_price = get_stock_price_with_smart_fallback("GOOG", entry_date)
    if not stock_price:
        print(f"❌ Could not get stock price for {entry_date}.")
        return None

    option_details = find_optimal_leaps_annual_january("GOOG", year, entry_date, exit_date, stock_price)
    if not option_details:
        print(f"❌ Could not find a valid LEAP for {year}.")
        return None

    entry_price = option_details['entry_price']
    
    if entry_price <= 0:
        print("❌ Invalid entry price of zero. Trade skipped.")
        return None

    cost_per_contract = (entry_price * 100) + COMMISSION_PER_CONTRACT
    num_contracts = floor(starting_capital / cost_per_contract)
    if num_contracts == 0:
        print("❌ Insufficient capital to purchase a single contract. Trade skipped.")
        return None

    exit_price = option_details['exit_price']
    
    split_info = detect_stock_split("GOOG", entry_date, exit_date)
    contract_multiplier = 100
    if split_info['has_split']:
        # For a 20:1 split, 1 contract becomes 20. Each controls 100 shares.
        # The total number of shares controlled is now 20 * 100 = 2000.
        # The exit_price is for ONE of the new contracts.
        # So, total proceeds = num_contracts * exit_price * (split_ratio * 100)
        print(f"   Split detected! Adjusting contract multiplier from 100 to {100 * split_info['split_ratio']}.")
        contract_multiplier = 100 * split_info['split_ratio']

    total_cost = num_contracts * ((entry_price * 100) + COMMISSION_PER_CONTRACT)
    leftover_cash = starting_capital - total_cost
    
    # Correctly calculate sale proceeds using the multiplier
    sale_proceeds = (num_contracts * exit_price * contract_multiplier) - (num_contracts * COMMISSION_PER_CONTRACT)
    final_capital = sale_proceeds + leftover_cash
    return_pct = ((final_capital - starting_capital) / starting_capital) * 100

    print(f"✅ Annual trade executed for {year}:")
    print(f"   Contracts purchased: {num_contracts} @ ${entry_price:.2f}")
    print(f"   Initial Capital: ${starting_capital:,.2f} -> Final Capital: ${final_capital:,.2f}")
    print(f"   Return: {return_pct:+.2f}%")

    return {
        "year": year,
        "strategy": "Annual Compounding",
        "final_capital": final_capital,
        "return_pct": return_pct,
    }

def analyze_year_compounding_quarterly(year: int, starting_capital: float) -> Optional[Dict[str, Any]]:
    """
    Analyzes the Compounding Quarterly Rolling Strategy for a single year.
    """
    print(f"\n🔄 COMPOUNDING QUARTERLY ANALYSIS: {year}")
    print("-" * 80)

    available_capital = starting_capital
    total_trades = 0

    q_dates = [
        get_first_trading_day_of_year("GOOG", year),
        get_last_trading_day_of_quarter("GOOG", year, 1),
        get_last_trading_day_of_quarter("GOOG", year, 2),
        get_last_trading_day_of_quarter("GOOG", year, 3),
        get_most_recent_trading_day("GOOG") if year == datetime.now().year else get_last_trading_day_of_year("GOOG", year)
    ]

    if None in q_dates:
        print(f"❌ Could not determine all quarterly trading dates for {year}.")
        return None

    for i in range(4):
        q_num = i + 1
        entry_date = q_dates[i]
        exit_date = q_dates[i+1]

        if not entry_date or not exit_date or entry_date >= exit_date:
            continue

        print(f"\n--- Q{q_num} Trade ({entry_date} -> {exit_date}) ---")
        print(f"   Starting Q{q_num} capital: ${available_capital:,.2f}")

        stock_price = get_stock_price_with_smart_fallback("GOOG", entry_date)
        if not stock_price:
            print(f"   ❌ Could not get stock price for {entry_date}. Capital carries over.")
            continue

        trade_details = execute_single_quarterly_trade("GOOG", entry_date, exit_date, stock_price)
        if not trade_details:
            print(f"   ❌ Could not find a valid trade for Q{q_num}. Capital carries over.")
            continue

        entry_price = trade_details['entry_price']
        
        if entry_price <= 0:
            print("   ❌ Invalid entry price of zero. Capital carries over.")
            continue

        cost_per_contract = (entry_price * 100) + COMMISSION_PER_CONTRACT
        num_contracts = floor(available_capital / cost_per_contract)
        if num_contracts == 0:
            print("   ❌ Insufficient capital for a contract. Capital carries over.")
            continue

        total_trades += 1
        exit_price = trade_details['exit_price']
        
        split_info = detect_stock_split("GOOG", entry_date, exit_date)
        contract_multiplier = 100
        if split_info['has_split']:
            print(f"   Split detected! Adjusting contract multiplier from 100 to {100 * split_info['split_ratio']}.")
            contract_multiplier = 100 * split_info['split_ratio']

        total_cost = num_contracts * ((entry_price * 100) + COMMISSION_PER_CONTRACT)
        leftover_cash = available_capital - total_cost
        
        # Correctly calculate sale proceeds using the multiplier
        sale_proceeds = (num_contracts * exit_price * contract_multiplier) - (num_contracts * COMMISSION_PER_CONTRACT)
        available_capital = sale_proceeds + leftover_cash
        
        print(f"   Q{q_num} trade executed: {num_contracts} contracts bought @ ${entry_price:.2f}, sold @ ${exit_price:.2f}")
        print(f"   End of Q{q_num} capital: ${available_capital:,.2f}")

    if total_trades == 0:
        return None

    final_capital = available_capital
    return_pct = ((final_capital - starting_capital) / starting_capital) * 100

    print(f"\n✅ Quarterly strategy completed for {year}:")
    print(f"   Initial Capital: ${starting_capital:,.2f} -> Final Capital: ${final_capital:,.2f}")
    print(f"   Return: {return_pct:+.2f}%")

    return {
        "year": year,
        "strategy": "Quarterly Compounding",
        "final_capital": final_capital,
        "return_pct": return_pct,
    }

def display_compounding_comparison_results(annual_results: List[Dict], quarterly_results: List[Dict]) -> None:
    print("\n\n" + "="*80)
    print("||" + " COMPOUNDING STRATEGY BACKTEST RESULTS ".center(76) + "||")
    print("="*80)
    header = f"{'Year':<7} | {'Strategy':<22} | {'Final Capital':>18} | {'Yearly Return':>18}"
    print(header)
    print("-" * 80)
    all_years = sorted(list(set([r['year'] for r in annual_results] + [r['year'] for r in quarterly_results])))
    for year in all_years:
        annual_data = next((r for r in annual_results if r['year'] == year), None)
        quarterly_data = next((r for r in quarterly_results if r['year'] == year), None)
        if annual_data:
            print(f"{annual_data['year']:<7} | {annual_data['strategy']:<22} | ${annual_data['final_capital']:>17,.2f} | {annual_data['return_pct']:>16.2f}%")
        if quarterly_data:
            print(f"{'':<7} | {quarterly_data['strategy']:<22} | ${quarterly_data['final_capital']:>17,.2f} | {quarterly_data['return_pct']:>16.2f}%")
        if annual_data or quarterly_data:
             print("-" * 80)

def main():
    parser = argparse.ArgumentParser(description='Compounding LEAPS Strategy Backtester (Gemini Version)')
    parser.add_argument('--capital', type=float, default=100000.0, help='Starting capital for each year.')
    args = parser.parse_args()

    print("♊️ GEMINI'S COMPOUNDING LEAPS BACKTESTER (v7 - Final)")
    print("=" * 80)
    if not ensure_theta_terminal_running():
        print("❌ Critical Error: Could not connect to ThetaTerminal. Aborting.")
        return
    
    years_to_test = [2022]
    print(f"📅 Testing year: {years_to_test[0]}")
    print(f"💰 Starting capital per year: ${args.capital:,.2f}")
    print("=" * 80)

    all_annual_results = []
    all_quarterly_results = []
    for year in years_to_test:
        annual_result = analyze_year_compounding_annual(year, args.capital)
        if annual_result:
            all_annual_results.append(annual_result)
        quarterly_result = analyze_year_compounding_quarterly(year, args.capital)
        if quarterly_result:
            all_quarterly_results.append(quarterly_result)
            
    if all_annual_results or all_quarterly_results:
        display_compounding_comparison_results(all_annual_results, all_quarterly_results)
    else:
        print("\n❌ No results were generated for any strategy.")

    print("\n✅ Backtesting complete.")

if __name__ == "__main__":
    main()
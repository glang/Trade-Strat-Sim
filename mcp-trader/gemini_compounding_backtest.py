#!/usr/bin/env python3
"""
Gemini's Implementation of a Compounding LEAPS Backtester (v3)

This script implements and backtests two LEAPS (Long-term Equity
AnticiPation Securities) strategies using a capital management model.
It simulates how a portfolio would grow by reinvesting proceeds from
trades throughout the year.

This version incorporates the improved logic from GTC.md, including
refactored functions and robust edge case handling. It also includes
a --quiet flag to suppress verbose output for a cleaner user experience.
"""

import argparse
import time
from math import floor
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Any, Optional

# --- Reuse existing, tested functions from the project ---
from accurate_optimized_leaps import (
    ensure_theta_terminal_running,
    find_optimal_leaps_annual_january,
    get_expirations_available_on_date,
    find_closest_expiration_date,
    get_bulk_eod_data,
    filter_itm_calls_from_bulk,
    get_bulk_at_time_quotes,
    extract_precise_entry_price_from_bulk,
    get_exit_price_individual,
    ENTRY_TIME_MS
)
from market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_most_recent_trading_day,
    get_last_trading_day_of_quarter
)
from smart_leaps_backtest import get_stock_price_with_smart_fallback

# --- New Refactored Helper Functions (as per GTC.md) ---

def find_best_quarterly_option(symbol: str, entry_date: str, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """
    Finds the optimal ~15-month LEAP option for a given entry date.
    This function is responsible for selecting the expiration and strike.
    """
    entry_dt = datetime.strptime(entry_date, '%Y%m%d').date()
    target_15_months = entry_dt + relativedelta(months=15)
    one_year_later = entry_dt + timedelta(days=365)

    all_expirations = get_expirations_available_on_date(symbol, entry_date, quiet=quiet)
    if not all_expirations:
        return None

    leaps_expirations = [exp for exp in all_expirations if exp >= one_year_later]
    if not leaps_expirations:
        return None

    closest_exp_obj = find_closest_expiration_date(leaps_expirations, target_15_months)
    if not closest_exp_obj:
        return None
    
    exp_date = closest_exp_obj.strftime('%Y%m%d')
    
    stock_price = get_stock_price_with_smart_fallback(symbol, entry_date, quiet=quiet)
    if not stock_price:
        return None

    entry_bulk_eod = get_bulk_eod_data(symbol, exp_date, entry_date, entry_date, quiet=quiet)
    if not entry_bulk_eod:
        return None

    valid_itm_calls = filter_itm_calls_from_bulk(entry_bulk_eod, stock_price, quiet=quiet)
    if not valid_itm_calls:
        return None

    # Select the optimal strike (closest to the stock price)
    optimal_call = valid_itm_calls[0]
    
    return {
        "expiration": exp_date,
        "strike": optimal_call['strike'],
        "stock_price_entry": stock_price
    }

def get_option_prices(symbol: str, option_details: Dict[str, Any], entry_date: str, exit_date: str, quiet: bool = False) -> Optional[Dict[str, float]]:
    """
    Gets the precise entry and exit prices for a given option contract.
    """
    exp_date = option_details['expiration']
    strike = option_details['strike']

    # Get precise entry price
    entry_quotes = get_bulk_at_time_quotes(symbol, exp_date, entry_date, ENTRY_TIME_MS, quiet=quiet)
    entry_price = extract_precise_entry_price_from_bulk(entry_quotes, strike, quiet=quiet)
    
    # Get exit price
    exit_price = get_exit_price_individual(symbol, exp_date, strike, exit_date, quiet=quiet)

    if entry_price is None or exit_price is None:
        return None

    return {"entry_price": entry_price, "exit_price": exit_price}


# --- Main Analysis Functions ---

def analyze_year_compounding_annual(year: int, starting_capital: float, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """
    Analyzes the Compounding Annual Strategy for a single year.
    """
    if not quiet:
        print(f"\n📈 COMPOUNDING ANNUAL ANALYSIS: {year}")
        print("-" * 80)

    entry_date = get_first_trading_day_of_year("GOOG", year, quiet=quiet)
    exit_date = get_most_recent_trading_day("GOOG", quiet=quiet) if year == datetime.now().year else get_last_trading_day_of_year("GOOG", year, quiet=quiet)
    if not entry_date or not exit_date:
        if not quiet: print(f"❌ Could not determine trading dates for {year}.")
        return None

    stock_price = get_stock_price_with_smart_fallback("GOOG", entry_date, quiet=quiet)
    if not stock_price:
        if not quiet: print(f"❌ Could not get stock price for {entry_date}.")
        return None

    option_details = find_optimal_leaps_annual_january("GOOG", year, entry_date, exit_date, stock_price, quiet=quiet)
    if not option_details:
        if not quiet: print(f"❌ Could not find a valid LEAP for {year}.")
        return None

    entry_price = option_details['entry_price']
    
    # --- Edge Case Handling ---
    if entry_price <= 0:
        if not quiet: print("❌ Invalid entry price of zero. Trade skipped.")
        return None

    num_contracts = floor(starting_capital / entry_price)
    if num_contracts == 0:
        if not quiet: print("❌ Insufficient capital to purchase a single contract. Trade skipped.")
        return None

    # --- Execute with capital management ---
    exit_price = option_details['exit_price']
    total_cost = num_contracts * entry_price
    leftover_cash = starting_capital - total_cost
    sale_proceeds = num_contracts * exit_price
    final_capital = sale_proceeds + leftover_cash
    return_pct = ((final_capital - starting_capital) / starting_capital) * 100

    if not quiet:
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

def analyze_year_compounding_quarterly(year: int, starting_capital: float, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """
    Analyzes the Compounding Quarterly Rolling Strategy for a single year.
    """
    if not quiet:
        print(f"\n🔄 COMPOUNDING QUARTERLY ANALYSIS: {year}")
        print("-" * 80)

    available_capital = starting_capital
    total_trades = 0

    q_dates = [
        get_first_trading_day_of_year("GOOG", year, quiet=quiet),
        get_last_trading_day_of_quarter("GOOG", year, 1, quiet=quiet),
        get_last_trading_day_of_quarter("GOOG", year, 2, quiet=quiet),
        get_last_trading_day_of_quarter("GOOG", year, 3, quiet=quiet),
        get_most_recent_trading_day("GOOG", quiet=quiet) if year == datetime.now().year else get_last_trading_day_of_year("GOOG", year, quiet=quiet)
    ]

    if None in q_dates:
        if not quiet: print(f"❌ Could not determine all quarterly trading dates for {year}.")
        return None

    for i in range(4):
        q_num = i + 1
        entry_date = q_dates[i]
        exit_date = q_dates[i+1]

        if not entry_date or not exit_date or entry_date >= exit_date:
            continue

        if not quiet:
            print(f"\n--- Q{q_num} Trade ({entry_date} -> {exit_date}) ---")
            print(f"   Starting Q{q_num} capital: ${available_capital:,.2f}")

        option_details = find_best_quarterly_option("GOOG", entry_date, quiet=quiet)
        if not option_details:
            if not quiet: print(f"   ❌ Could not find a valid LEAP for Q{q_num}. Capital carries over.")
            continue
        
        prices = get_option_prices("GOOG", option_details, entry_date, exit_date, quiet=quiet)
        if not prices:
            if not quiet: print(f"   ❌ Could not get prices for the selected LEAP. Capital carries over.")
            continue

        entry_price = prices['entry_price']
        
        # --- Edge Case Handling ---
        if entry_price <= 0:
            if not quiet: print("   ❌ Invalid entry price of zero. Capital carries over.")
            continue

        num_contracts = floor(available_capital / entry_price)
        if num_contracts == 0:
            if not quiet: print("   ❌ Insufficient capital for a contract. Capital carries over.")
            continue

        # --- Execute with capital management ---
        total_trades += 1
        exit_price = prices['exit_price']
        total_cost = num_contracts * entry_price
        leftover_cash = available_capital - total_cost
        sale_proceeds = num_contracts * exit_price
        available_capital = sale_proceeds + leftover_cash
        
        if not quiet:
            print(f"   Q{q_num} trade executed: {num_contracts} contracts bought @ ${entry_price:.2f}, sold @ ${exit_price:.2f}")
            print(f"   End of Q{q_num} capital: ${available_capital:,.2f}")

    if total_trades == 0:
        return None

    final_capital = available_capital
    return_pct = ((final_capital - starting_capital) / starting_capital) * 100

    if not quiet:
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
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose logging and only show the final results.')
    args = parser.parse_args()

    print("♊️ GEMINI'S COMPOUNDING LEAPS BACKTESTER (v3)")
    print("=" * 80)
    if not ensure_theta_terminal_running(quiet=args.quiet):
        print("❌ Critical Error: Could not connect to ThetaTerminal. Aborting.")
        return
    current_year = datetime.now().year
    years_to_test = list(range(2016, current_year + 1))
    
    if not args.quiet:
        print(f"📅 Testing years: {years_to_test[0]} to {years_to_test[-1]}")
        print(f"💰 Starting capital per year: ${args.capital:,.2f}")
        print("=" * 80)
    else:
        print("Running backtest in quiet mode... (this may take a minute)")

    all_annual_results = []
    all_quarterly_results = []
    for year in years_to_test:
        annual_result = analyze_year_compounding_annual(year, args.capital, quiet=args.quiet)
        if annual_result:
            all_annual_results.append(annual_result)
        quarterly_result = analyze_year_compounding_quarterly(year, args.capital, quiet=args.quiet)
        if quarterly_result:
            all_quarterly_results.append(quarterly_result)
            
    if all_annual_results or all_quarterly_results:
        display_compounding_comparison_results(all_annual_results, all_quarterly_results)
    else:
        print("\n❌ No results were generated for any strategy.")

    print("\n✅ Backtesting complete.")

if __name__ == "__main__":
    main()
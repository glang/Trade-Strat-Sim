#!/usr/bin/env python3
"""
Compounding LEAPS Backtest with Capital Management

This script implements two position-sized LEAPS strategies that demonstrate
how capital constraints affect real-world trading performance:

1. **Compounding Annual Strategy**: Uses full available capital for a single
   January LEAPS trade, held for the entire year.

2. **Compounding Quarterly Rolling Strategy**: Compounds capital quarterly by
   rolling into new ~15-month LEAPS positions, with capital growing or shrinking
   based on trade performance.

Key features:
- Realistic position sizing based on available capital
- Transaction costs (commissions) included
- Liquidity constraints to prevent unrealistic large positions
- Each year starts with fresh $100,000 capital to isolate market condition effects
- Uses all existing functions from accurate_optimized_leaps.py for data accuracy

The goal is to analyze how these strategies perform under different market
conditions (bull vs bear years) with realistic capital constraints.
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import math

# --- Path setup to allow importing from the backtesting_engine package ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# Import all necessary functions from the existing backtest
from src.backtesting_engine.accurate_optimized_leaps import (
    find_optimal_leaps_annual_january,
    execute_single_quarterly_trade,
    ensure_theta_terminal_running,
)
from src.backtesting_engine.market_days_cache import (
    get_first_trading_day_of_year,
    get_last_trading_day_of_year,
    get_first_trading_day_of_quarter,
    get_last_trading_day_of_quarter,
    get_most_recent_trading_day,
)
from src.backtesting_engine.smart_leaps_backtest import (
    get_stock_price_with_smart_fallback,
    analyze_smart_cache
)


# Constants
DEFAULT_STARTING_CAPITAL = 100000.0
COMMISSION_PER_CONTRACT = 0.35  # Realistic commission cost
MAX_CONTRACTS_PER_TRADE = 999999  # Effectively unlimited
TARGET_CAPITAL_UTILIZATION = 1.0  # Use 100% of capital
SYMBOL = "GOOG"

def calculate_position_size(available_capital: float, entry_price_per_contract: float, 
                          commission_per_contract: float = COMMISSION_PER_CONTRACT,
                          max_contracts_per_trade: int = MAX_CONTRACTS_PER_TRADE) -> Dict[str, Any]:
    """
    Calculate realistic position size with constraints.
    
    Args:
        available_capital: Available capital for trading
        entry_price_per_contract: Entry price per option contract
        
    Returns:
        Dict containing position size details
    """
    if entry_price_per_contract <= 0:
        return {
            'num_contracts': 0,
            'total_entry_cost': 0.0,
            'total_commission': 0.0,
            'total_cost': 0.0,
            'leftover_cash': available_capital,
            'capital_utilization': 0.0,
            'error': 'Invalid entry price'
        }
    
    # Calculate maximum contracts based on target utilization
    target_capital = available_capital * TARGET_CAPITAL_UTILIZATION
    
    # Account for commission in position sizing
    cost_per_contract = entry_price_per_contract + commission_per_contract
    
    # Calculate maximum affordable contracts
    max_affordable = int(target_capital / cost_per_contract)
    
    # Apply liquidity constraint
    num_contracts = min(max_affordable, max_contracts_per_trade)
    
    # Calculate actual costs
    total_entry_cost = num_contracts * entry_price_per_contract
    total_commission = num_contracts * commission_per_contract
    total_cost = total_entry_cost + total_commission
    leftover_cash = available_capital - total_cost
    capital_utilization = (total_cost / available_capital) * 100
    
    return {
        'num_contracts': num_contracts,
        'total_entry_cost': total_entry_cost,
        'total_commission': total_commission,
        'total_cost': total_cost,
        'leftover_cash': leftover_cash,
        'capital_utilization': capital_utilization,
        'error': None
    }

def calculate_exit_proceeds(num_contracts: int, exit_price_per_contract: float,
                          commission_per_contract: float = COMMISSION_PER_CONTRACT) -> Dict[str, Any]:
    """
    Calculate exit proceeds including commission costs.
    
    Args:
        num_contracts: Number of contracts to sell
        exit_price_per_contract: Exit price per contract
        
    Returns:
        Dict containing exit proceeds details
    """
    gross_proceeds = num_contracts * exit_price_per_contract
    exit_commission = num_contracts * commission_per_contract
    net_proceeds = gross_proceeds - exit_commission
    
    return {
        'gross_proceeds': gross_proceeds,
        'exit_commission': exit_commission,
        'net_proceeds': net_proceeds
    }

def analyze_year_compounding_annual(year: int, starting_capital: float, 
                                  commission_per_contract: float = COMMISSION_PER_CONTRACT,
                                  max_contracts_per_trade: int = MAX_CONTRACTS_PER_TRADE,
                                  quiet: bool = True) -> Dict[str, Any]:
    """
    Analyze a single year using the Compounding Annual Strategy.
    
    Uses full available capital for a single January LEAPS trade.
    
    Args:
        year: Year to analyze
        starting_capital: Starting capital for the year
        quiet: If True, suppress verbose output
        
    Returns:
        Dict containing year's performance results
    """
    
    # Get entry and exit dates for the year
    entry_date = get_first_trading_day_of_year(SYMBOL, year, quiet=quiet)
    
    # For current year, use most recent trading day; for past years, use last trading day
    current_year = datetime.now().year
    if year == current_year:
        exit_date = get_most_recent_trading_day(SYMBOL, quiet=quiet)
    else:
        exit_date = get_last_trading_day_of_year(SYMBOL, year, quiet=quiet)
    
    if not entry_date or not exit_date:
        error_msg = f"Could not determine entry ({entry_date}) or exit ({exit_date}) dates"
        return {
            'year': year,
            'strategy': 'Annual Compounding',
            'starting_capital': starting_capital,
            'final_capital': starting_capital,
            'yearly_return_pct': 0.0,
            'num_contracts': 0,
            'total_cost': 0.0,
            'capital_utilization': 0.0,
            'error': error_msg,
            'trade_details': None
        }
    
    # Get stock price for entry day
    stock_price = get_stock_price_with_smart_fallback(SYMBOL, entry_date, quiet=quiet)
    if not stock_price:
        error_msg = f"Could not get stock price for {entry_date}"
        return {
            'year': year,
            'strategy': 'Annual Compounding',
            'starting_capital': starting_capital,
            'final_capital': starting_capital,
            'yearly_return_pct': 0.0,
            'num_contracts': 0,
            'total_cost': 0.0,
            'capital_utilization': 0.0,
            'error': error_msg,
            'trade_details': None
        }
    
    if not quiet:
        print(f"📅 Entry: {entry_date}, Exit: {exit_date}")
        print(f"📊 Stock Price: ${stock_price:.2f}")
    
    # Get the optimal annual January LEAPS trade
    annual_result = find_optimal_leaps_annual_january(SYMBOL, year, entry_date, exit_date, stock_price, quiet=quiet)
    
    if not annual_result or annual_result.get('error'):
        error_msg = annual_result.get('error', 'Unknown error') if annual_result else 'No trade data available'
        return {
            'year': year,
            'strategy': 'Annual Compounding',
            'starting_capital': starting_capital,
            'final_capital': starting_capital,  # No change if no trade
            'yearly_return_pct': 0.0,
            'num_contracts': 0,
            'total_cost': 0.0,
            'capital_utilization': 0.0,
            'error': error_msg,
            'trade_details': None
        }
    
    # Add dates to the result for detailed logging
    annual_result['entry_date'] = entry_date
    annual_result['exit_date'] = exit_date

    # Calculate position size
    entry_price = annual_result['entry_price']
    position_info = calculate_position_size(starting_capital, entry_price, commission_per_contract, max_contracts_per_trade)
    
    if position_info['error'] or position_info['num_contracts'] == 0:
        error_msg = position_info['error'] or 'No contracts can be purchased'
        # Still pass trade_details for logging purposes
        return {
            'year': year,
            'strategy': 'Annual Compounding',
            'starting_capital': starting_capital,
            'final_capital': starting_capital,
            'yearly_return_pct': 0.0,
            'num_contracts': 0,
            'total_cost': 0.0,
            'capital_utilization': 0.0,
            'error': error_msg,
            'trade_details': annual_result
        }
    
    # Calculate exit proceeds
    exit_price = annual_result['exit_price']
    exit_info = calculate_exit_proceeds(position_info['num_contracts'], exit_price, commission_per_contract)
    
    # Calculate final capital and return
    final_capital = exit_info['net_proceeds'] + position_info['leftover_cash']
    yearly_return_pct = ((final_capital - starting_capital) / starting_capital) * 100
    
    return {
        'year': year,
        'strategy': 'Annual Compounding',
        'starting_capital': starting_capital,
        'final_capital': final_capital,
        'yearly_return_pct': yearly_return_pct,
        'num_contracts': position_info['num_contracts'],
        'total_cost': position_info['total_cost'],
        'capital_utilization': position_info['capital_utilization'],
        'gross_proceeds': exit_info['gross_proceeds'],
        'net_proceeds': exit_info['net_proceeds'],
        'total_commissions': position_info['total_commission'] + exit_info['exit_commission'],
        'leftover_cash': position_info['leftover_cash'],
        'error': None,
        'trade_details': annual_result
    }

def analyze_year_compounding_quarterly(year: int, starting_capital: float,
                                     commission_per_contract: float = COMMISSION_PER_CONTRACT,
                                     max_contracts_per_trade: int = MAX_CONTRACTS_PER_TRADE,
                                     quiet: bool = True) -> Dict[str, Any]:
    """
    Analyze a single year using the Compounding Quarterly Rolling Strategy.
    
    Compounds capital quarterly by rolling into new ~15-month LEAPS positions.
    
    Args:
        year: Year to analyze
        starting_capital: Starting capital for the year
        quiet: If True, suppress verbose output
        
    Returns:
        Dict containing year's performance results
    """
    
    available_capital = starting_capital
    quarterly_trades = []
    total_commissions = 0.0
    
    most_recent_day = None
    if year == datetime.now().year:
        most_recent_day = get_most_recent_trading_day(SYMBOL, quiet=quiet)

    # Execute quarterly trades
    for quarter in range(1, 5):
        if not quiet:
            print(f"\n📅 Quarter {quarter} - Available Capital: ${available_capital:,.2f}")
        
        # Get entry and exit dates for the quarter
        entry_date = get_first_trading_day_of_quarter(SYMBOL, year, quarter, quiet=quiet)
        
        # For the current year, skip future quarters
        if most_recent_day and entry_date and entry_date > most_recent_day:
            if not quiet: print(f"Skipping Q{quarter} as it is in the future.")
            break

        exit_date = get_last_trading_day_of_quarter(SYMBOL, year, quarter, quiet=quiet)

        # For the current year, cap the exit date at the most recent trading day
        if most_recent_day and exit_date and exit_date > most_recent_day:
            exit_date = most_recent_day
        
        if not entry_date or not exit_date:
            error_msg = f"Could not determine Q{quarter} dates: entry={entry_date}, exit={exit_date}"
            if not quiet:
                print(f"❌ Q{quarter} Date Error: {error_msg}")
            quarterly_trades.append({
                'quarter': quarter,
                'available_capital': available_capital,
                'error': error_msg,
                'num_contracts': 0,
                'capital_after_trade': available_capital
            })
            continue

        # If entry and exit dates are the same or invalid, it's not a valid trade period
        if entry_date >= exit_date:
            if not quiet: print(f"Skipping Q{quarter} as entry date ({entry_date}) is on or after exit date ({exit_date}).")
            continue
        
        # Get stock price for entry day
        stock_price = get_stock_price_with_smart_fallback(SYMBOL, entry_date, quiet=quiet)
        if not stock_price:
            error_msg = f"Could not get stock price for {entry_date}"
            if not quiet:
                print(f"❌ Q{quarter} Stock Price Error: {error_msg}")
            quarterly_trades.append({
                'quarter': quarter,
                'available_capital': available_capital,
                'error': error_msg,
                'num_contracts': 0,
                'capital_after_trade': available_capital
            })
            continue
        
        if not quiet:
            print(f"📅 Q{quarter} Entry: {entry_date}, Exit: {exit_date}")
            print(f"📊 Stock Price: ${stock_price:.2f}")
        
        # Get the quarterly trade
        quarterly_result = execute_single_quarterly_trade(SYMBOL, entry_date, exit_date, stock_price, quiet=quiet)
        
        if not quarterly_result or quarterly_result.get('error'):
            error_msg = quarterly_result.get('error', 'Unknown error') if quarterly_result else 'No trade data available'
            if not quiet:
                print(f"❌ Q{quarter} Trade Failed: {error_msg}")
            
            # Record failed trade
            quarterly_trades.append({
                'quarter': quarter,
                'available_capital': available_capital,
                'error': error_msg,
                'num_contracts': 0,
                'capital_after_trade': available_capital
            })
            continue
        
        # Calculate position size
        entry_price = quarterly_result['entry_price']
        position_info = calculate_position_size(available_capital, entry_price, commission_per_contract, max_contracts_per_trade)
        
        if position_info['error'] or position_info['num_contracts'] == 0:
            error_msg = position_info['error'] or 'No contracts can be purchased'
            if not quiet:
                print(f"❌ Q{quarter} Position Sizing Failed: {error_msg}")
            
            quarterly_trades.append({
                'quarter': quarter,
                'available_capital': available_capital,
                'error': error_msg,
                'num_contracts': 0,
                'capital_after_trade': available_capital
            })
            continue
        
        # Calculate exit proceeds
        exit_price = quarterly_result['exit_price']
        exit_info = calculate_exit_proceeds(position_info['num_contracts'], exit_price, commission_per_contract)
        
        # Update capital for next quarter
        new_available_capital = exit_info['net_proceeds'] + position_info['leftover_cash']
        trade_return_pct = ((new_available_capital - available_capital) / available_capital) * 100
        
        # Track commissions
        trade_commissions = position_info['total_commission'] + exit_info['exit_commission']
        total_commissions += trade_commissions
        
        if not quiet:
            print(f"   Entry: {entry_date} @ ${entry_price:.2f}")
            print(f"   Exit:  {exit_date} @ ${exit_price:.2f}")
            print(f"   Contracts: {position_info['num_contracts']:,}")
            print(f"   Capital Utilization: {position_info['capital_utilization']:.1f}%")
            print(f"   Trade Return: {trade_return_pct:+.1f}%")
            print(f"   New Capital: ${new_available_capital:,.2f}")
        
        # Record trade details
        trade_summary = {
            'quarter': quarter,
            'available_capital': available_capital,
            'num_contracts': position_info['num_contracts'],
            'capital_utilization': position_info['capital_utilization'],
            'trade_return_pct': trade_return_pct,
            'capital_after_trade': new_available_capital,
            'commissions': trade_commissions,
            'error': None
        }
        trade_summary.update(quarterly_result)  # Merge the detailed results
        quarterly_trades.append(trade_summary)
        
        # Update capital for next quarter
        available_capital = new_available_capital
    
    # Calculate final results
    final_capital = available_capital
    yearly_return_pct = ((final_capital - starting_capital) / starting_capital) * 100
    
    return {
        'year': year,
        'strategy': 'Quarterly Rolling Compounding',
        'starting_capital': starting_capital,
        'final_capital': final_capital,
        'yearly_return_pct': yearly_return_pct,
        'total_commissions': total_commissions,
        'quarterly_trades': quarterly_trades,
        'error': None
    }

def display_detailed_trades(results: List[Dict[str, Any]]) -> None:
    """
    Display a detailed log of every single trade made.
    
    Args:
        results: List of yearly results from both strategies
    """
    print("\n" + "="*100)
    print("TRADE LOG: DETAILED BREAKDOWN OF EVERY TRADE")
    print("="*100)

    # Sort results by year and then by strategy for consistent ordering
    results.sort(key=lambda x: (x['year'], x['strategy']))

    for result in results:
        if result.get('error') and not result.get('trade_details') and not result.get('quarterly_trades'):
            print(f"\n--- {result['year']} {result['strategy']} ---")
            print(f"  ERROR: {result['error']}")
            continue

        if result['strategy'] == 'Annual Compounding':
            print(f"\n--- {result['year']} {result['strategy']} ---")
            trade = result.get('trade_details')
            if not trade or result.get('num_contracts', 0) == 0:
                print(f"  No trade was executed. Reason: {result.get('error', 'Not specified')}")
                continue
            
            # Construct contract name
            exp_date_str = trade['expiration']
            exp_date_short = datetime.strptime(exp_date_str, '%Y%m%d').strftime('%y%m%d')
            strike_formatted = f"{trade['original_strike']:08d}"
            contract_name = f"{SYMBOL}{exp_date_short}C{strike_formatted}"

            print(f"  Trade: Buy {result['num_contracts']} contracts of {contract_name} on {trade['entry_date']}")
            print(f"  Entry Details:")
            print(f"    - Option Price: ${trade['entry_price']:.2f}")
            print(f"    - Total Cost: ${result['total_cost']:,.2f} (incl. ${result.get('total_commissions', 0):,.2f} commission)")
            print(f"    - Capital Utilized: {result['capital_utilization']:.1f}%")
            print(f"  Exit Details:")
            print(f"    - Exit Date: {trade['exit_date']}")
            print(f"    - Option Price: ${trade['exit_price']:.2f}")
            print(f"    - Net Proceeds: ${result['net_proceeds']:,.2f}")
            print(f"  Outcome:")
            print(f"    - P/L: ${result['final_capital'] - result['starting_capital']:+,.2f}")
            print(f"    - Return: {result['yearly_return_pct']:+.1f}%")

        elif result['strategy'] == 'Quarterly Rolling Compounding':
            print(f"\n--- {result['year']} {result['strategy']} ---")
            trades = result.get('quarterly_trades', [])
            if not trades:
                print("  No trades were executed.")
                continue

            for trade in trades:
                if trade.get('error'):
                    print(f"\n  --- Q{trade['quarter']} ---")
                    print(f"    ERROR: {trade['error']}")
                    continue
                
                # Construct contract name from trade data
                exp_date_str = trade['expiration']
                exp_date_short = datetime.strptime(exp_date_str, '%Y%m%d').strftime('%y%m%d')
                # The key is 'original_strike' in some dicts, 'strike' in others. Let's check for both.
                strike = trade.get('original_strike') or trade.get('strike')
                strike_formatted = f"{strike:08d}"
                contract_name = f"{SYMBOL}{exp_date_short}C{strike_formatted}"

                print(f"\n  --- Q{trade['quarter']} Trade ---")
                print(f"    Trade: Buy {trade['num_contracts']} contracts of {contract_name} on {trade['entry_date']}")
                print(f"    Entry Details:")
                print(f"      - Option Price: ${trade['entry_price']:.2f}")
                print(f"      - Capital Deployed: ${trade['available_capital']:,.2f}")
                print(f"    Exit Details:")
                print(f"      - Exit Date: {trade['exit_date']}")
                print(f"      - Option Price: ${trade['exit_price']:.2f}")
                print(f"    Outcome:")
                print(f"      - P/L for quarter: ${trade['capital_after_trade'] - trade['available_capital']:+,.2f}")
                print(f"      - Return for quarter: {trade['trade_return_pct']:+.1f}%")
                print(f"      - Capital after trade: ${trade['capital_after_trade']:,.2f}")


def display_compounding_comparison_results(results: List[Dict[str, Any]]) -> None:
    """
    Display a formatted comparison of compounding strategy results.
    
    Args:
        results: List of yearly results from both strategies
    """
    print("\n" + "="*100)
    print("🎯 COMPOUNDING LEAPS STRATEGIES COMPARISON")
    print("="*100)
    
    # Separate results by strategy
    annual_results = [r for r in results if r['strategy'] == 'Annual Compounding']
    quarterly_results = [r for r in results if r['strategy'] == 'Quarterly Rolling Compounding']
    
    # Sort by year
    annual_results.sort(key=lambda x: x['year'])
    quarterly_results.sort(key=lambda x: x['year'])
    
    print(f"\n📊 YEAR-BY-YEAR COMPARISON")
    print("-"*100)
    print(f"{'Year':<6} {'Annual Return':<15} {'Annual Capital':<18} {'Quarterly Return':<18} {'Quarterly Capital':<18}")
    print("-"*100)
    
    for i, year in enumerate(range(2016, 2026)):
        annual_result = next((r for r in annual_results if r['year'] == year), None)
        quarterly_result = next((r for r in quarterly_results if r['year'] == year), None)
        
        if annual_result and quarterly_result:
            annual_return = f"{annual_result['yearly_return_pct']:+.1f}%"
            annual_capital = f"${annual_result['final_capital']:,.0f}"
            quarterly_return = f"{quarterly_result['yearly_return_pct']:+.1f}%"
            quarterly_capital = f"${quarterly_result['final_capital']:,.0f}"
            
            print(f"{year:<6} {annual_return:<15} {annual_capital:<18} {quarterly_return:<18} {quarterly_capital:<18}")
    
    # Calculate aggregate statistics
    print("\n📈 STRATEGY PERFORMANCE SUMMARY")
    print("-"*60)
    
    def calculate_stats(strategy_results):
        if not strategy_results:
            return None
        
        returns = [r['yearly_return_pct'] for r in strategy_results if r['error'] is None]
        if not returns:
            return None
            
        winning_trades = [r for r in returns if r > 0]
        losing_trades = [r for r in returns if r < 0]
        
        return {
            'total_years': len(returns),
            'winning_years': len(winning_trades),
            'losing_years': len(losing_trades),
            'win_rate': (len(winning_trades) / len(returns)) * 100 if returns else 0,
            'average_return': sum(returns) / len(returns) if returns else 0,
            'average_winner': sum(winning_trades) / len(winning_trades) if winning_trades else 0,
            'average_loser': sum(losing_trades) / len(losing_trades) if losing_trades else 0,
            'best_year': max(returns) if returns else 0,
            'worst_year': min(returns) if returns else 0
        }
    
    annual_stats = calculate_stats(annual_results)
    quarterly_stats = calculate_stats(quarterly_results)
    
    if annual_stats and quarterly_stats:
        print(f"{'Metric':<25} {'Annual Strategy':<20} {'Quarterly Strategy':<20}")
        print("-"*60)
        print(f"{'Total Years':<25} {annual_stats['total_years']:<20} {quarterly_stats['total_years']:<20}")
        print(f"{'Win Rate':<25} {annual_stats['win_rate']:.1f}%{'':<15} {quarterly_stats['win_rate']:.1f}%{'':<15}")
        print(f"{'Average Return':<25} {annual_stats['average_return']:+.1f}%{'':<14} {quarterly_stats['average_return']:+.1f}%{'':<14}")
        print(f"{'Average Winner':<25} {annual_stats['average_winner']:+.1f}%{'':<14} {quarterly_stats['average_winner']:+.1f}%{'':<14}")
        print(f"{'Average Loser':<25} {annual_stats['average_loser']:+.1f}%{'':<14} {quarterly_stats['average_loser']:+.1f}%{'':<14}")
        print(f"{'Best Year':<25} {annual_stats['best_year']:+.1f}%{'':<14} {quarterly_stats['best_year']:+.1f}%{'':<14}")
        print(f"{'Worst Year':<25} {annual_stats['worst_year']:+.1f}%{'':<14} {quarterly_stats['worst_year']:+.1f}%{'':<14}")
    
    print("\n💡 CAPITAL EFFICIENCY INSIGHTS")
    print("-"*60)
    
    # Show commission impact
    total_annual_commissions = sum(r.get('total_commissions', 0) for r in annual_results)
    total_quarterly_commissions = sum(r.get('total_commissions', 0) for r in quarterly_results)
    
    print(f"Total Commissions Paid:")
    print(f"  Annual Strategy: ${total_annual_commissions:,.2f}")
    print(f"  Quarterly Strategy: ${total_quarterly_commissions:,.2f}")
    print(f"  Difference: ${total_quarterly_commissions - total_annual_commissions:+,.2f}")
    
    # Show capital utilization
    avg_annual_utilization = sum(r.get('capital_utilization', 0) for r in annual_results) / len(annual_results) if annual_results else 0
    
    quarterly_utilizations = []
    for qr in quarterly_results:
        if qr.get('quarterly_trades'):
            for trade in qr['quarterly_trades']:
                if trade.get('capital_utilization'):
                    quarterly_utilizations.append(trade['capital_utilization'])
    
    avg_quarterly_utilization = sum(quarterly_utilizations) / len(quarterly_utilizations) if quarterly_utilizations else 0
    
    print(f"\nAverage Capital Utilization:")
    print(f"  Annual Strategy: {avg_annual_utilization:.1f}%")
    print(f"  Quarterly Strategy: {avg_quarterly_utilization:.1f}%")

def main():
    """Main execution function with command-line argument parsing."""
    parser = argparse.ArgumentParser(description="Compounding LEAPS Backtesting with Capital Management")
    parser.add_argument('--capital', type=float, default=DEFAULT_STARTING_CAPITAL,
                        help=f'Starting capital for each year (default: ${DEFAULT_STARTING_CAPITAL:,.0f})')
    parser.add_argument('--start-year', type=int, default=2016,
                        help='Starting year for backtest (default: 2016)')
    parser.add_argument('--end-year', type=int, default=2025,
                        help='Ending year for backtest (default: 2025)')
    parser.add_argument('--commission', type=float, default=COMMISSION_PER_CONTRACT,
                        help=f'Commission per contract (default: ${COMMISSION_PER_CONTRACT})')
    parser.add_argument('--max-contracts', type=int, default=MAX_CONTRACTS_PER_TRADE,
                        help=f'Maximum contracts per trade (default: {MAX_CONTRACTS_PER_TRADE})')
    
    args = parser.parse_args()
    
    # Use local variables instead of modifying globals
    commission_per_contract = args.commission
    max_contracts_per_trade = args.max_contracts
    
    print(f"🎯 Running LEAPS Compounding Backtest ({args.start_year}-{args.end_year})")
    print("Processing... (this may take a few minutes)")
    
    # Ensure ThetaTerminal is running (silently)
    if not ensure_theta_terminal_running(quiet=True):
        print("❌ Failed to start ThetaTerminal. Please check your setup.")
        sys.exit(1)
    
    # Run backtests for all years
    all_results = []
    
    for year in range(args.start_year, args.end_year + 1):
        # Skip future years beyond current year
        if year > datetime.now().year:
            continue
            
        print(f"Processing {year}...", end=" ")
        
        # Run annual compounding strategy
        annual_result = analyze_year_compounding_annual(year, args.capital, commission_per_contract, max_contracts_per_trade, quiet=True)
        all_results.append(annual_result)
        
        # Run quarterly rolling compounding strategy
        quarterly_result = analyze_year_compounding_quarterly(year, args.capital, commission_per_contract, max_contracts_per_trade, quiet=True)
        all_results.append(quarterly_result)
        
        print("✓")
    
    # Display detailed trade log
    display_detailed_trades(all_results)
    
    # Display comparison results
    display_compounding_comparison_results(all_results)

if __name__ == "__main__":
    main()
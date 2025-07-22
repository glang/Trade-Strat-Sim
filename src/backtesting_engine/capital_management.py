"""
Capital Management Module for LEAPS Backtesting

This module provides standardized functions for handling the financial calculations
related to trading, including position sizing and calculating proceeds from a sale.
It is designed to be used by different backtesting scripts to ensure that the
core logic for capital management remains consistent.
"""

import math
from typing import Dict, Any, Optional

def calculate_position_size(
    available_capital: float,
    option_price: float,
    commission_per_contract: float = 0.35,
    max_contracts_per_trade: int = 999999
) -> Dict[str, Any]:
    """
    Calculates the number of contracts to purchase based on available capital.

    Args:
        available_capital: The total cash available for the trade.
        option_price: The price of a single option contract.
        commission_per_contract: The commission fee for buying one contract.
        max_contracts_per_trade: The maximum number of contracts allowed per trade.

    Returns:
        A dictionary containing the details of the position size.
    """
    if available_capital <= 0 or option_price <= 0:
        return {'error': 'Invalid capital or option price.', 'num_contracts': 0}

    # Each contract represents 100 shares
    cost_per_contract = (option_price * 100) + commission_per_contract

    if cost_per_contract > available_capital:
        return {
            'error': 'Insufficient capital to purchase a single contract.',
            'num_contracts': 0,
            'total_cost': 0,
            'total_commission': 0,
            'leftover_cash': available_capital,
            'capital_utilization': 0.0
        }

    num_contracts = int(available_capital // cost_per_contract)
    num_contracts = min(num_contracts, max_contracts_per_trade)

    if num_contracts == 0:
        return {
            'error': 'Calculated contracts is zero.',
            'num_contracts': 0,
            'total_cost': 0,
            'total_commission': 0,
            'leftover_cash': available_capital,
            'capital_utilization': 0.0
        }

    total_option_cost = num_contracts * option_price * 100
    total_commission = num_contracts * commission_per_contract
    grand_total_cost = total_option_cost + total_commission
    leftover_cash = available_capital - grand_total_cost
    capital_utilization = (grand_total_cost / available_capital) * 100

    return {
        'num_contracts': num_contracts,
        'total_cost': total_option_cost,
        'total_commission': total_commission,
        'leftover_cash': leftover_cash,
        'capital_utilization': capital_utilization,
        'error': None
    }

def calculate_exit_proceeds(
    num_contracts: int,
    exit_price: float,
    commission_per_contract: float = 0.35
) -> Dict[str, Any]:
    """
    Calculates the net proceeds from closing a position.

    Args:
        num_contracts: The number of contracts being sold.
        exit_price: The sale price of a single option contract.
        commission_per_contract: The commission fee for selling one contract.

    Returns:
        A dictionary containing the details of the exit proceeds.
    """
    if num_contracts <= 0:
        return {'error': 'Invalid number of contracts.', 'net_proceeds': 0}

    gross_proceeds = num_contracts * exit_price * 100
    exit_commission = num_contracts * commission_per_contract
    net_proceeds = gross_proceeds - exit_commission

    return {
        'gross_proceeds': gross_proceeds,
        'exit_commission': exit_commission,
        'net_proceeds': net_proceeds,
        'error': None
    }

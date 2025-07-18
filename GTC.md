# GTC.md - Gemini to Claude Implementation Plan (v2)

## 1. High-Level Objective: Evolving from Backtester to Analysis Platform

The project's next evolution is to transform it from a simple backtester that reports P&L into a sophisticated **Strategy Analysis and Optimization Platform**. The goal is to produce rich, contextual data that will allow an AI agent to perform a deep analysis of a strategy's performance, identify its strengths and weaknesses, and suggest concrete improvements.

This will be achieved by implementing three core features:
1.  **The Trade Journal:** A detailed log of every decision made.
2.  **Standard Financial Metrics:** A suite of professional metrics to evaluate risk and return.
3.  **Strategy Parameterization:** The ability to easily modify and test variations of a strategy.

---

## 2. Feature Specification: The Trade Journal

### a. Purpose and Rationale

The Trade Journal is the most critical new feature. A simple final P&L tells us *what* happened, but the journal will tell us *why*. By logging the context of every single trade, we provide the raw data needed for an AI to identify patterns and flaws in the strategy's logic.

### b. Implementation Details

The backtesting scripts (`run_..._backtest.py`) should be modified to produce a new output file alongside the console summary: `trade_journal.json`.

This file will be a JSON array containing one object for every **buy/sell cycle**.

### c. Data Schema for a Single Trade Log Entry

Each object in the `trade_journal.json` array must adhere to the following schema:

```json
{
  "strategy_name": "Quarterly Compounding",
  "year": 2023,
  "quarter": "Q1",
  "trade_trigger": "Initial position for the year",
  "entry_date": "20230103",
  "exit_date": "20230331",
  "market_context_at_entry": {
    "goog_price": 89.83,
    "vix_price": 22.9,  // Example: To be implemented later
    "market_sentiment": "Neutral" // Example: To be implemented later
  },
  "option_details": {
    "expiration": "20240315",
    "strike": 89.00,
    "type": "Call",
    "months_to_expiration": 14.4
  },
  "greeks_at_entry": {
    "delta": 0.68,
    "gamma": 0.015,
    "theta": -0.04,
    "vega": 0.25,
    "implied_volatility": 45.5
  },
  "position_sizing": {
    "capital_at_start_of_trade": 100000.00,
    "entry_price_per_contract": 16.05,
    "contracts_purchased": 623,
    "total_cost": 9999.15,
    "leftover_cash": 0.85
  },
  "outcome": {
    "exit_price_per_contract": 12.50,
    "pnl_per_contract": -3.55,
    "total_pnl": -2211.65,
    "return_on_trade_capital": -22.1
  }
}
```
*(**Note to Implementer:** The `vix_price` and `market_sentiment` fields are placeholders for future enhancements and can be set to `null` or omitted for now. The key is to build the structure to support them later.)*

---

## 3. Feature Specification: Standard Financial Metrics

### a. Purpose and Rationale

Professional traders and quantitative analysts use a standard set of metrics to evaluate a strategy's performance in a way that goes beyond simple returns. By calculating these, we allow the AI to speak the language of finance and provide much more insightful feedback (e.g., "This strategy has a high return but a poor Sharpe Ratio, meaning you are taking on too much risk for the reward you are getting.")

### b. Implementation Details

A new function, `calculate_performance_metrics(yearly_results: list) -> dict`, should be created. This function will take the list of final yearly return percentages and calculate the following metrics. The results should be added to the main console output at the end of the backtest.

### c. Required Metrics and Formulas

1.  **Sharpe Ratio:**
    *   **Formula:** `(Mean of Yearly Returns - Risk-Free Rate) / Standard Deviation of Yearly Returns`
    *   **Implementation Note:** Assume a `Risk-Free Rate` of **2%** (or `0.02`). This value should be a constant that is easy to change later.

2.  **Sortino Ratio:**
    *   **Formula:** `(Mean of Yearly Returns - Risk-Free Rate) / Standard Deviation of *Negative* Yearly Returns`
    *   **Implementation Note:** This is similar to the Sharpe Ratio but only considers the standard deviation of the losing years, which some consider a better measure of "bad" volatility.

3.  **Maximum Drawdown:**
    *   **Formula:** The largest percentage drop from a portfolio's peak value to its subsequent lowest value (trough).
    *   **Implementation Note:** This requires tracking the portfolio's value over time. For the annual strategy, this is simple (start, end). For the quarterly strategy, the calculation must track the capital value at the end of *each quarter* across all years to find the largest peak-to-trough drop. This is the most complex metric to implement.

4.  **Best Year & Worst Year:**
    *   Simply the `max()` and `min()` of the yearly return percentages.

5.  **Win Rate %:**
    *   The percentage of years where the return was greater than 0.

---

## 4. Feature Specification: Strategy Parameterization

### a. Purpose and Rationale

Currently, the strategy rules are "hardcoded" (e.g., "buy a ~15-month LEAP"). To turn the backtester into a true laboratory, these rules must become parameters that can be changed easily from the command line. This allows us and the AI to test hypotheses and optimize the strategy (e.g., "Would a 12-month LEAP have performed better than a 15-month one?").

### b. Implementation Details

The main backtesting scripts must be updated to accept new command-line arguments. The core logic must then be modified to use the values from these arguments instead of the hardcoded constants.

### c. Required Parameters to Implement

1.  **`--months-to-expiration`**
    *   **Description:** The target time to expiration, in months, for the quarterly rolling strategy.
    *   **Type:** `int`
    *   **Default:** `15`
    *   **Effect:** This will change the `target_15_months` calculation in the option selection logic.

2.  **`--itm-aggressiveness`**
    *   **Description:** A factor that controls how deep In-the-Money the selected option should be.
    *   **Type:** `float`
    *   **Default:** `1.0`
    *   **Effect:** This will modify the strike selection logic. The target strike will be `stock_price * itm_aggressiveness`. A value of `1.0` maintains the current logic (closest to the money). A value of `0.90` would select a deeper ITM option with a strike price around 90% of the stock price.

3.  **`--capital-utilization`**
    *   **Description:** The percentage of available capital to use for each trade.
    *   **Type:** `float`
    *   **Default:** `0.95` (for Claude's implementation) or `1.0` (for Gemini's).
    *   **Effect:** This will directly affect the position sizing calculation.

This detailed plan provides a clear and comprehensive guide for implementing the next generation of features for our trading strategy analysis platform.

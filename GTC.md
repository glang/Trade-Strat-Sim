# GTC.md - Gemini to Claude Implementation Plan

## 1. High-Level Objective

The goal is to create a new backtesting mode that simulates two LEAPS options strategies with capital management. This will provide a more realistic measure of performance by tracking a portfolio's value as it compounds throughout the year.

The two new strategies to be implemented are:
1.  **Compounding Annual Strategy**
2.  **Compounding Quarterly Rolling Strategy**

The final output should be a side-by-side comparison of these two new strategies only.

## 2. Core Logic & Strategy Definitions

### a. Starting Capital & Annual Reset

- For each year in the backtest (e.g., 2016, 2017, etc.), both strategies will start with a fresh capital base of **$100,000**.
- Profits or losses from one year **do not** carry over to the next. This allows for a clean, year-by-year comparison of performance under different market conditions.

### b. Compounding Annual Strategy

This strategy involves a single trade per year, using the full capital available.

1.  **Initialization:** Start the year with `$100,000` in capital.
2.  **Option Selection:** On the first trading day of the year, use the existing `find_optimal_leaps_annual_january` function to identify the single best January LEAP option and its precise entry price.
3.  **Position Sizing:**
    -   Calculate the maximum number of contracts that can be purchased without exceeding the available capital.
    -   `num_contracts = floor(available_capital / entry_price_per_contract)`
    -   **Rule:** If the `entry_price_per_contract` is zero, the trade is skipped for the year.
4.  **Execution (Buy):**
    -   Calculate the total cost: `total_cost = num_contracts * entry_price_per_contract`.
    -   Calculate leftover cash: `leftover_cash = available_capital - total_cost`.
5.  **Execution (Sell):**
    -   On the last trading day of the year, "sell" all `num_contracts` at the determined exit price.
    -   Calculate the total sale proceeds: `sale_proceeds = num_contracts * exit_price_per_contract`.
6.  **Final Calculation:**
    -   Calculate the final capital for the year: `final_capital = sale_proceeds + leftover_cash`.
    -   Calculate the yearly return: `return_pct = ((final_capital - starting_capital) / starting_capital) * 100`.

### c. Compounding Quarterly Rolling Strategy

This strategy involves rolling the position every quarter, compounding the capital with each trade.

1.  **Initialization:** Start the year with `$100,000` in capital.
2.  **Q1 Trade:**
    -   **Option Selection:** On the first trading day of Q1, find the optimal ~15-month LEAP and its entry price.
    -   **Position Sizing & Execution:** Buy as many contracts as possible with the initial `$100,000`. Record the number of contracts, total cost, and leftover cash.
    -   **Rule:** If the entry price is zero or if the available capital is less than the price of a single contract, no trade is placed. The capital simply rolls over to the next quarter.
3.  **End of Q1 / Start of Q2:**
    -   **Sell:** "Sell" all contracts held from Q1.
    -   **Update Capital:** The new available capital is `sale_proceeds_from_Q1 + leftover_cash_from_Q1`.
    -   **Option Selection:** Find the new optimal ~15-month LEAP for the Q2 trade.
    -   **Position Sizing & Execution:** Buy as many contracts as possible with the newly updated capital, following the same rules as above. Record the new number of contracts and new leftover cash.
4.  **Repeat for Q3 and Q4:** Continue this process of selling, updating capital, and buying new positions at the end of Q2 and Q3.
5.  **Final Calculation:** After the final trade of Q4 is closed, the `final_capital` is the sum of the final sale proceeds plus the leftover cash from the Q4 purchase. Calculate the total yearly return based on this final capital.

## 3. Implementation Plan for Claude

To implement this, we should modify the `accurate_optimized_leaps.py` script. The best approach is to create new, high-level "compounding" functions that wrap smaller, refactored helper functions.

### Step 1: Refactor Existing Functions (Recommended)

To avoid code duplication and improve modularity, it is highly recommended to first break down the monolithic `execute_single_quarterly_trade` function into smaller, more focused helper functions.

-   **`find_best_quarterly_option(symbol: str, entry_date: str) -> Optional[dict]:`**
    -   This new function would be responsible *only* for finding the optimal ~15-month LEAP and its metadata (expiration, strike). It would not handle any pricing.
-   **`get_option_prices(option_details: dict, entry_date: str, exit_date: str) -> Optional[dict]:`**
    -   This function would take the details of an option and return its precise entry and exit prices.

This refactoring will make the new compounding logic much cleaner and easier to implement.

### Step 2: Create New Analysis Functions

Create two new primary functions to house the compounding logic.

**`analyze_year_compounding_annual(year: int, starting_capital: float) -> dict:`**
- This function will contain the logic for the **Compounding Annual Strategy**.
- It will call `find_optimal_leaps_annual_january` to get the option details and prices.
- It will then perform the position sizing (checking for zero price and sufficient capital), capital calculations, and return a dictionary with the results for the year.

**`analyze_year_compounding_quarterly(year: int, starting_capital: float) -> dict:`**
- This function will contain the logic for the **Compounding Quarterly Rolling Strategy**.
- It will loop through the four quarters of the year.
- In each loop, it will:
    1.  Call the newly refactored helper functions to get the option and its prices.
    2.  Calculate position size based on the *current* available capital, explicitly handling the "insufficient capital" and "zero price" edge cases.
    3.  Update the capital for the next quarter (`new_capital = sale_proceeds + leftover_cash`).
- It will return a summary dictionary for the entire year's quarterly performance.

### Step 3: Add a New Command-Line Argument

Modify the `main()` function to accept a new command-line flag to trigger this new backtest mode.

-   Add an argument: `parser.add_argument('--compounding', action='store_true', help='Run the backtest with compounding capital management.')`
-   Add another argument for the capital amount, with a default: `parser.add_argument('--capital', type=float, default=100000.0, help='Set the starting capital for compounding mode.')`

### Step 4: Update the Main Execution Logic

In the `main()` function, add a condition to check for the new flag.

```python
if args.compounding:
    # Call the new compounding analysis functions
    # e.g., annual_results = analyze_year_compounding_annual(year, args.capital)
    # ...
    # Call the new display function for compounding results
else:
    # Run the original, simple backtest logic
    # ...
```

### Step 5: Create a New Display Function

Create a new function to display the results of the compounding backtest, as requested.

**`display_compounding_comparison_results(results: List[Dict]) -> None:`**
- This function will take a list of results from the new analysis functions.
- It will print a clean, formatted table with the following columns:
    - `Year`
    - `Strategy` (e.g., "Annual Compounding")
    - `Final Capital`
    - `Yearly Return %`
- This keeps the output clean and focused on the new strategies.

This plan provides a clear and robust path to implementing the requested features.
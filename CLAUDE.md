# LEAPS Options Backtesting System - Complete Guide

## 1. Project Overview
This project implements and backtests LEAPS (Long-term Equity Anticipation Securities) trading strategies for GOOG. The primary focus is on **compounding capital management** to simulate realistic portfolio performance under different market conditions.

The main implementation is found in `claude_compounding_leaps_backtest.py`, which was developed to be a more feature-rich and realistic simulation than the original backtester.

## 2. Implemented Strategies

The backtester supports two primary strategies, which are compared on a year-by-year basis, each starting with a fresh capital base to isolate market conditions.

#### a. Compounding Annual Strategy
- A single trade is placed per year using the full available capital.
- **Entry:** First trading day of the year.
- **Option:** A January LEAP for the following year is selected (ITM, strike closest to stock price).
- **Position Sizing:** Uses 95% of available capital to buy as many contracts as possible, up to a liquidity limit of 500 contracts. A commission of $0.35 per contract is factored in.
- **Exit:** The position is held for the entire year and sold on the last trading day.

#### b. Compounding Quarterly Rolling Strategy
- A more active strategy that rolls the LEAPS position every quarter to maintain a consistent time to expiration (~15 months).
- **Cycle:** Four trades are placed per year. At the end of each quarter, the current position is sold, and the entire proceeds (plus any leftover cash) are reinvested in a new position.
- **Option Selection:** For each quarter, a new ~15-month LEAP is selected.
- **Position Sizing:** The same 95% capital utilization, liquidity, and commission rules are applied for each of the four trades.

## 3. Getting Started: A Guide for New Agents

This guide provides everything needed to set up and run the backtesting project.

### a. Prerequisites

*   **Python 3.11+**: Ensure a recent version of Python is installed.
    ```bash
    python3 --version
    ```
*   **Java Development Kit (JDK)**: The ThetaData terminal is a Java application.
    ```bash
    java -version
    ```
    If Java is not installed, use a package manager like Homebrew (`brew install openjdk`) or download it directly.

### b. Environment File

The project requires API keys stored in a `.env` file in the **project's root directory**.

1.  From the project's root directory, copy the example:
    ```bash
    cp mcp-trader/.env.example .env
    ```
2.  Edit the new `.env` file and add your credentials.

### c. Install Dependencies

The project's dependencies are listed in `pyproject.toml`. You can use `pip` to install them.

1.  From the `mcp-trader` directory, run:
    ```bash
    pip3 install "aiohttp>=3.12.13" "numpy~=1.26.4" "pandas>=2.3.0" "pandas-ta>=0.3.14b" "python-dotenv>=1.0.1" "thetadata==0.9.11" "yfinance>=0.2.63" "python-dateutil>=2.8.2" "requests"
    ```

### d. Run the Backtest

1.  **Set Permissions:** Make the ThetaData startup script executable (only needs to be done once):
    ```bash
    chmod +x mcp-trader/start_theta.sh
    ```
2.  **Initialize Caches:** The first time you run, you must populate the market data caches:
    ```bash
    python3 mcp-trader/market_days_cache.py
    ```
3.  **Execute the Backtest:** Run Claude's implementation:
    ```bash
    python3 mcp-trader/claude_compounding_leaps_backtest.py
    ```
    The script will automatically start the ThetaData terminal and run the full backtest from 2016-2025.

## 4. System Architecture & Technical Details

This section details the "how" and "why" of the system's design.

### a. Data Sources

*   **ThetaData (Primary):** Used for its comprehensive historical options data (8+ years), bulk API endpoints for performance, and the `list/dates/stock/trade` endpoint for authoritative trading day detection.
*   **Tiingo (Secondary):** Used for stock price verification and as a fallback.

### b. Core Logic

*   **Auto-Start:** The scripts automatically check if the ThetaData terminal is running and will launch it if needed.
*   **Market Day Caching:** The first run fetches all historical trading days and caches them permanently in `market_days_cache.json` for instant lookups on subsequent runs.
*   **Price Extraction:** Entry prices are based on the `Ask` price at 10:00 AM EST to simulate a realistic purchase. Exit prices are based on the End-of-Day `Close` or `Bid` price.
*   **Stock Split Handling:** The logic correctly identifies and adjusts for the GOOG 20:1 stock split that occurred on July 15, 2022.

### c. Critical Data Formats

*   **Dates:** All API calls use the `YYYYMMDD` format (e.g., `20230102`).
*   **Strike Prices:** ThetaData uses a millidollar format, where the dollar amount is multiplied by 1000 (e.g., a $170 strike is represented as `170000`).

## 5. Project Files

*   **`claude_compounding_leaps_backtest.py`**: The main, feature-rich implementation.
*   **`gemini_compounding_backtest.py`**: A parallel implementation created for comparison.
*   **`accurate_optimized_leaps.py`**: The original V1 backtester and a library of core functions.
*   **`market_days_cache.py` / `smart_leaps_backtest.py`**: Helper modules for caching.
*   **`GTC.md`**: The planning document that led to the compounding implementations.
*   **`start_theta.sh`**: Securely starts the ThetaData terminal using credentials from `.env`.

This consolidated document now provides a complete and accurate overview of the project in its current state.

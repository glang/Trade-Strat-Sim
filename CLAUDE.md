# LEAPS Options Backtesting System - Complete Guide

## 1. Project Overview
This project implements and backtests LEAPS (Long-term Equity Anticipation Securities) trading strategies for GOOG. The primary focus is on **compounding capital management** to simulate realistic portfolio performance under different market conditions.

The main backtesting scripts are located in the `scripts/` directory.

## 2. Implemented Strategies

The backtester supports two primary strategies, which are compared on a year-by-year basis, each starting with a fresh capital base to isolate market conditions.

#### a. Compounding Annual Strategy
- A single trade is placed per year using the full available capital.
- **Entry:** First trading day of the year.
- **Option:** A January LEAP for the following year is selected (ITM, strike closest to stock price).
- **Position Sizing:** Buys as many contracts as possible with the available capital, factoring in a commission of $0.35 per contract.
- **Exit:** The position is held for the entire year and sold on the last trading day.

#### b. Compounding Quarterly Rolling Strategy
- A more active strategy that rolls the LEAPS position every quarter to maintain a consistent time to expiration (~15 months).
- **Cycle:** Four trades are placed per year. At the end of each quarter, the current position is sold, and the entire proceeds are reinvested in a new position.
- **Option Selection:** For each quarter, a new ~15-month LEAP is selected.
- **Position Sizing:** The same commission and capital rules are applied for each of the four trades.

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
    cp .env.example .env
    ```
2.  Edit the new `.env` file and add your credentials.

### c. Install Dependencies

The project's dependencies are listed in `pyproject.toml`. You can use `pip` to install them.

1.  From the project's root directory, run:
    ```bash
    pip3 install "aiohttp>=3.12.13" "numpy~=1.26.4" "pandas>=2.3.0" "pandas-ta>=0.3.14b" "python-dotenv>=1.0.1" "thetadata==0.9.11" "yfinance>=0.2.63" "python-dateutil>=2.8.2" "requests"
    ```

### d. Run the Backtest

1.  **Set Permissions:** Make the ThetaData startup script executable (only needs to be done once):
    ```bash
    chmod +x scripts/start_theta.sh
    ```
2.  **Initialize Caches:** The first time you run, you must populate the market data caches. Note that the caching scripts are now part of the `backtesting_engine` and are not run directly. The main backtest scripts will populate the cache automatically on their first run.

3.  **Execute the Backtest:** Run one of the primary backtesting scripts:
    ```bash
    # To run Claude's implementation (with commissions, etc.)
    python3 scripts/run_claude_backtest.py

    # To run Gemini's implementation (a cleaner, direct model)
    python3 scripts/run_gemini_backtest.py
    ```
    The script will automatically start the ThetaData terminal and run the full backtest from 2016-2025.

## 4. System Architecture & Technical Details

This section details the "how" and "why" of the system's design.

### a. Data Sources

*   **ThetaData (Primary):** Used for its comprehensive historical options data, bulk API endpoints, and authoritative trading day detection.
*   **Tiingo (Secondary):** Used for stock price verification.

### b. Core Logic

*   **Backtesting Engine:** All core logic (data fetching, caching, option selection, pricing) is located in the `src/backtesting_engine` package.
*   **Auto-Start:** The scripts automatically check if the ThetaData terminal is running and will launch it if needed via `scripts/start_theta.sh`.
*   **Market Day Caching:** The first run fetches all historical trading days and caches them permanently in `market_days_cache.json` for instant lookups.
*   **Stock Split Handling:** The logic correctly identifies and adjusts for the GOOG 20:1 stock split on July 15, 2022.

### c. Critical Data Formats

*   **Dates:** All API calls use the `YYYYMMDD` format (e.g., `20230102`).
*   **Strike Prices:** ThetaData uses a millidollar format, where the dollar amount is multiplied by 1000 (e.g., a $170 strike is `170000`).

## 5. Project Files

*   **`pyproject.toml`**: Project dependencies and configuration.
*   **`CLAUDE.md` / `GTC.md`**: Project documentation and planning files.
*   **`src/backtesting_engine/`**: The core Python package containing all the logic for data handling and strategy components.
*   **`scripts/`**: Contains the runnable backtesting scripts (`run_claude_backtest.py`, `run_gemini_backtest.py`) and helper scripts (`start_theta.sh`).
*   **`docs/`**: Contains supplementary documentation, including the local copy of the ThetaData API docs.
*   **`ThetaTerminal.jar`**: The Java application required to connect to the ThetaData API.

This consolidated document now provides a complete and accurate overview of the project in its current, restructured state.
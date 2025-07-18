# LEAPS Options Backtesting System - Complete Guide

## 1. Project Overview
This project implements and backtests LEAPS (Long-term Equity Anticipation Securities) trading strategies for GOOG. The primary focus is on **compounding capital management** to simulate realistic portfolio performance under different market conditions.

The main backtesting scripts, which represent two different AI implementations of the same core strategies, are located in the `scripts/` directory.

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

This guide provides a complete, step-by-step process to set up and run the backtesting project from a fresh clone.

### a. Prerequisites

1.  **Python 3.11+**: Ensure a recent version of Python is installed.
    ```bash
    python3 --version
    ```
2.  **Java Development Kit (JDK)**: The ThetaData terminal is a Java application.
    ```bash
    java -version
    ```
    If Java is not installed, use a package manager like Homebrew (`brew install openjdk`) or download it directly.
3.  **ThetaTerminal.jar**: Verify that the `ThetaTerminal.jar` file is present in the project's root directory. It is a critical component for connecting to the data provider.

### b. Environment File

The project requires API keys stored in a `.env` file in the **project's root directory**.

1.  From the project's root directory, copy the example:
    ```bash
    cp .env.example .env
    ```
2.  Edit the new `.env` file with a text editor and add your credentials.

### c. Install Dependencies

The project's dependencies are listed in `pyproject.toml`.

1.  From the project's root directory, run the following command to install all necessary packages:
    ```bash
    pip3 install "aiohttp>=3.12.13" "numpy~=1.26.4" "pandas>=2.3.0" "pandas-ta>=0.3.14b" "python-dotenv>=1.0.1" "thetadata==0.9.11" "yfinance>=0.2.63" "python-dateutil>=2.8.2" "requests"
    ```

### d. Run the Backtest

1.  **Set Permissions:** Make the ThetaData startup script executable (this only needs to be done once):
    ```bash
    chmod +x scripts/start_theta.sh
    ```
2.  **Execute a Backtest:** Run one of the primary backtesting scripts. The scripts will automatically start the ThetaData terminal and populate data caches on their first run.

    *   **To run Claude's implementation (Feature-Rich Simulation):**
        This version includes realistic trading constraints like capital utilization targets and liquidity limits, in addition to commissions. It provides a more conservative and real-world view of performance.
        ```bash
        python3 scripts/run_claude_backtest.py
        ```

    *   **To run Gemini's implementation (Direct Strategy Model):**
        This version is a direct and literal implementation of the core strategy, including commissions but without the additional constraints. It is useful for analyzing the performance of the raw strategy itself.
        ```bash
        python3 scripts/run_gemini_backtest.py
        ```

## 4. System Architecture & Technical Details

*   **Backtesting Engine:** All core logic (data fetching, caching, option selection, pricing) is located in the `src/backtesting_engine` package.
*   **Auto-Start:** The scripts automatically check if the ThetaData terminal is running and will launch it if needed via `scripts/start_theta.sh`.
*   **Market Day Caching:** The first run fetches all historical trading days and caches them permanently in `market_days_cache.json` for instant lookups.
*   **Stock Split Handling:** The logic correctly identifies and adjusts for the GOOG 20:1 stock split on July 15, 2022.

## 5. Project Files

*   **`pyproject.toml`**: Project dependencies and configuration.
*   **`CLAUDE.md` / `GTC.md`**: Project documentation and planning files.
*   **`src/backtesting_engine/`**: The core Python package containing all the logic for data handling and strategy components.
*   **`scripts/`**: Contains the runnable backtesting scripts and helper scripts.
*   **`docs/`**: Contains supplementary documentation.
*   **`ThetaTerminal.jar`**: The Java application required to connect to the ThetaData API.

This consolidated document now provides a complete and accurate overview of the project in its current, restructured state.

# LEAPS Options Backtesting Platform - Complete Guide

## 1. Project Overview

This project provides a robust platform for backtesting LEAPS (Long-term Equity Anticipation Securities) trading strategies on GOOG. Its primary focus is on **compounding capital management** to simulate realistic portfolio performance under different market conditions.

The platform features two distinct backtesting scripts, located in the `scripts/` directory. While both test the same core strategies, they represent different philosophies: one as a direct, unconstrained model, and the other as a feature-rich, realistic simulation framework.

## 2. Core Strategies

The backtester supports two primary strategies. To isolate the performance characteristics of each market year, both strategies begin with a fresh $100,000 capital base at the start of every year.

#### a. Compounding Annual Strategy
- A single trade is placed per year using the full available capital.
- **Entry:** First trading day of the year.
- **Option:** A January LEAP for the *following* year is selected (typically ITM, with a strike closest to the stock price).
- **Position Sizing:** Buys as many contracts as possible with the available capital, factoring in a commission of $0.35 per contract.
- **Exit:** The position is held for the entire year and sold on the last trading day.

#### b. Compounding Quarterly Rolling Strategy
- A more active strategy that rolls the LEAPS position every quarter to maintain a consistent time to expiration (~15 months).
- **Cycle:** Four trades are placed per year. At the end of each quarter, the current position is sold, and the entire proceeds are reinvested.
- **Option Selection:** For each quarter, a new ~15-month LEAP is selected.
- **Position Sizing:** The same capital and commission rules are applied for each of the four trades, allowing capital to compound (or deplete) intra-year.

## 3. Getting Started: A Step-by-Step Guide

This guide provides a complete process to set up and run the backtesting platform from a fresh clone.

### a. Prerequisites

1.  **Python 3.11+**: Ensure a recent version of Python is installed.
    ```bash
    python3 --version
    ```
2.  **Java Development Kit (JDK)**: The ThetaData terminal is a Java application.
    ```bash
    java -version
    ```
3.  **ThetaTerminal.jar**: Verify that the `ThetaTerminal.jar` file is present in the project's root directory.

### b. Environment File

The project requires API keys stored in a `.env` file in the project's root directory.

1.  Copy the example file:
    ```bash
    cp .env.example .env
    ```
2.  Edit the new `.env` file and add your API credentials.

### c. Install Dependencies

The project's dependencies are listed in `pyproject.toml`.

1.  From the project's root directory, run the following command:
    ```bash
    pip3 install "aiohttp>=3.12.13" "numpy~=1.26.4" "pandas>=2.3.0" "pandas-ta>=0.3.14b" "python-dotenv>=1.0.1" "thetadata==0.9.11" "yfinance>=0.2.63" "python-dateutil>=2.8.2" "requests"
    ```

### d. Run a Backtest

1.  **Set Permissions:** Make the ThetaData startup script executable (one-time setup):
    ```bash
    chmod +x scripts/start_theta.sh
    ```
2.  **Execute a Backtest:** The scripts automatically start the ThetaData terminal.

    *   **To run the Gemini implementation (Direct Strategy Model):**
        This version is a direct, literal implementation of the core strategies. It is useful for analyzing the performance of the raw strategy itself without additional constraints.
        ```bash
        python3 scripts/run_gemini_backtest.py
        ```

    *   **To run the Claude implementation (Feature-Rich Simulation):**
        This version is a more advanced simulation framework. It includes command-line configurability, a framework for liquidity limits, and provides a much more detailed and insightful final report.
        ```bash
        python3 scripts/run_claude_backtest.py --start-year 2016 --end-year 2025
        ```

## 4. System Architecture

*   **`src/backtesting_engine/`**: The core Python package containing all logic for data handling, option selection, capital management, and trade execution.
*   **`scripts/`**: Contains the two runnable backtesting scripts (`run_gemini_backtest.py` and `run_claude_backtest.py`).
*   **`CLAUDE.md` / `GTC.md`**: Project documentation and planning files.
*   **`ThetaTerminal.jar`**: The Java application required to connect to the ThetaData API.
*   **Auto-Start:** The scripts automatically check if the ThetaData terminal is running and will launch it if needed.
*   **Caching:** The first run fetches all historical trading days and caches them in `market_days_cache.json` for instant lookups.

## 5. Implementation Comparison: Gemini vs. Claude

The two implementations serve different purposes. Gemini's script provides a raw benchmark, while Claude's script is a superior tool for in-depth, realistic analysis.

| Feature | Gemini Implementation | Claude Implementation |
| :--- | :--- | :--- |
| **Philosophy** | Direct, raw strategy backtest | Realistic, feature-rich simulation |
| **Configuration** | Hardcoded values | Command-line arguments |
| **Reporting** | Basic table of results | Multi-section analytical report |
| **Insights** | Shows final P/L | Shows P/L, **plus** commission costs & trade volume |
| **Realism** | Assumes infinite liquidity | Includes a framework for liquidity limits |

### Post-Correction Analysis (2022 Results)

After fixing a critical bug in the Claude implementation, the numerical results of the two scripts are now nearly identical, as they both use the same underlying `capital_management` module. The differences are now in reporting and features, not core logic.

| Strategy (2022) | Final Return (Gemini) | Final Return (Claude) |
| :--- | :--- | :--- |
| **Annual** | `-100.05%` | `-100.1%` |
| **Quarterly**| `-94.89%` | `-95.4%` |

The key takeaway is no longer about divergent results, but about the **quality of the simulation.** The Claude implementation is considered more "realistic" because:
1.  **It models constraints:** It has the built-in capability to model liquidity limits, a crucial factor for any real-world trading system.
2.  **It provides deeper insights:** Its reporting separates signal from noise, highlighting the significant impact of transaction costs (commissions) on the quarterly strategy—a vital piece of analysis that the Gemini report omits.

This updated document provides a complete and accurate overview of the project in its current, corrected state.
# LEAPS Options Strategy Analysis Platform

## 1. Project Overview

This project provides a robust platform for backtesting and analyzing various LEAPS (Long-term Equity Anticipation Securities) trading strategies on GOOG. It has evolved from a simple backtester into a comprehensive analysis suite that allows users to explore the impact of capital management, strike selection, and advanced strategies like covered calls.

The platform is divided into two main categories of tools: **Core Backtesting Models** that simulate portfolio performance over time, and **Advanced Strategy Analysis** scripts that perform focused analysis on specific trading mechanics.

## 2. Core Backtesting Models

These scripts simulate two primary, capital-compounding strategies. To isolate the performance characteristics of each market year, both strategies begin with a fresh $100,000 capital base at the start of every year.

#### a. Compounding Annual Strategy
- A single trade is placed per year using the full available capital.
- **Entry:** First trading day of the year.
- **Option:** A January LEAP for the *following* year is selected (typically ITM, with a strike closest to the stock price).
- **Exit:** The position is held for the entire year and sold on the last trading day.

#### b. Compounding Quarterly Rolling Strategy
- A more active strategy that rolls the LEAPS position every quarter to maintain a consistent time to expiration (~15 months).
- **Cycle:** Four trades are placed per year. At the end of each quarter, the current position is sold, and the entire proceeds are reinvested.

These core strategies are implemented in two scripts that represent different simulation philosophies:
- **`run_gemini_backtest.py` (Direct Model):** A direct, literal implementation of the core strategies. It is useful for analyzing the performance of the raw strategy itself without additional constraints. It features hardcoded values and a basic results table.
- **`run_claude_backtest.py` (Feature-Rich Simulation):** A more advanced simulation framework. It includes command-line configurability, a framework for liquidity limits, and provides a much more detailed and insightful final report that includes metrics like commission costs and trade volume.

## 3. Advanced Strategy Analysis

Beyond the core compounding strategies, the platform now includes specialized scripts for deeper analysis of options trading mechanics.

#### a. Strike Selection Comparison (`run_strike_comparison_backtest.py`)
This script analyzes how the selection of a strike price impacts the performance of the annual LEAPS strategy. It compares three distinct approaches:
- **Barely ITM (In-The-Money):** The standard strategy of selecting the strike closest to, but below, the stock price.
- **Most OTM (Out-of-The-Money):** A high-risk, high-reward strategy that selects the call option with the absolute highest available strike price.
- **Mid-Point:** A balanced approach that calculates the average between the ITM and OTM strikes and selects the closest available option, using trade volume as a tie-breaker.

#### b. Poor Man's Covered Call (PMCC) Validation (`run_simple_pmcc_test.py`)
This script serves as a focused validation test for a PMCC strategy. For a single year, it simulates:
1.  Buying the standard deep ITM LEAPS call.
2.  Selling a single, liquid, ~35 DTE, ~0.30 delta call against it.
3.  It then calculates the P&L for both legs of the trade to verify the core logic before running a full-scale, monthly-rolling backtest.

## 4. Getting Started: A Step-by-Step Guide

This guide provides a complete process to set up and run the backtesting platform from a fresh clone.

### a. Prerequisites
1.  **Python 3.11+**
2.  **Java Development Kit (JDK)**
3.  **`ThetaTerminalv3.jar`** file in the project's root directory.

### b. Environment File and Credentials
The project requires API keys stored in a `.env` file in the project's root directory.
```bash
cp .env.example .env
# Edit the new .env file and add your API credentials.
```

**ThetaTerminalv3 Credentials Setup:**
After setting up your `.env` file, create a credentials file for ThetaTerminal:
```bash
# Create creds.txt from your .env variables
source .env && echo "$THETADATA_USERNAME" > creds.txt && echo "$THETADATA_PASSWORD" >> creds.txt
```

**Note:** The `creds.txt` file is automatically excluded from git commits via `.gitignore` to protect your credentials.

### c. Install Dependencies

#### Required Python Packages
The platform requires several Python packages for data processing, API connectivity, and system management:

```bash
# Core dependencies
pip3 install httpx numpy~=1.26.4 pandas>=2.3.0 pandas-ta>=0.3.14b python-dotenv>=1.0.1 thetadata==0.9.11 yfinance>=0.2.63 python-dateutil>=2.8.2 psutil
```

**Package Purposes:**
- `httpx` - A modern HTTP client for Python, used for all ThetaData API v3 requests.
- `numpy` - Numerical computing foundation
- `pandas` - Data manipulation and analysis
- `pandas-ta` - Technical analysis indicators
- `python-dotenv` - Environment variable management
- `thetadata` - ThetaData API client library (Note: not used for v3 API calls)
- `yfinance` - Yahoo Finance data fallback
- `python-dateutil` - Date/time parsing utilities
- `psutil` - System process management (for ThetaTerminal)

#### macOS Setup Notes
If you encounter pip installation issues on macOS:

1. **Install pip if missing:**
   ```bash
   # Download and install pip
   curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
   python3 get-pip.py --user
   rm get-pip.py  # Clean up after installation
   ```

2. **Handle externally-managed environment:**
   ```bash
   # If you get "externally-managed-environment" error, add this flag:
   pip3 install [packages] --break-system-packages
   
   # Or use virtual environment (recommended):
   python3 -m venv venv
   source venv/bin/activate
   pip install [packages]
   ```

3. **macOS-specific dependencies:**
   ```bash
   # Install Xcode command line tools if needed
   xcode-select --install
   ```

### d. Running the Tools
**Execute a Backtest:**
    ```bash
    # To run the feature-rich compounding simulation
    python3 scripts/run_claude_backtest.py --start-year 2016 --end-year 2025

    # To run the strike selection comparison
    python3 scripts/run_strike_comparison_backtest.py

    # To run the simple PMCC validation test
    python3 scripts/run_simple_pmcc_test.py --year 2023
    ```

## 5. System Architecture

*   **`src/backtesting_engine/`**: The core Python package containing all logic for data handling, option selection, capital management, and trade execution.
*   **`scripts/`**: Contains the runnable backtesting scripts, including `run_gemini_backtest.py`, `run_claude_backtest.py`, `run_strike_comparison_backtest.py`, and `run_simple_pmcc_test.py`.
*   **`CLAUDE.md` / `GTC.md`**: Project documentation and planning files.
*   **`ThetaTerminalv3.jar`**: The Java application required to connect to the ThetaData API (v3).
*   **Robust Connection Management:** The platform uses `ThetaConnectionManager` which provides:
    - Automatic ThetaTerminalv3 startup and shutdown
    - Intelligent process detection and cleanup
    - ThetaTerminalv3 credentials file handling (`creds.txt`)
    - v3 API endpoint compatibility (port 25503) and request logic
    - Stale process detection and cleanup
    - Comprehensive error reporting and connection verification
    - Signal handling for clean exits
*   **Caching:** The first run fetches all historical trading days and caches them in `market_days_cache.json` for instant lookups.

### Important Note on API Usage

The ThetaData v3 API endpoints have distinct and specific query parameter requirements. Do not assume that parameters (e.g., `date` vs. `start_date`) are consistent across different endpoints.

When implementing or modifying an API call, it is **mandatory** to:
1.  Consult the specific documentation page for that exact endpoint.
2.  Refer to the **Sample Code** section on that page as the "gold standard" reference for implementation. This ensures that all required parameters are provided in the correct format.

# LEAPS Options Strategy Analysis Platform

## 1. Project Overview

This project provides a robust platform for backtesting and analyzing various LEAPS (Long-term Equity Anticipation Securities) trading strategies on GOOG. It has evolved from a simple backtester into a comprehensive analysis suite that allows users to explore the impact of capital management, strike selection, and advanced strategies like Poor Man's Covered Calls (PMCC).

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
1. Buying the standard deep ITM LEAPS call.
2. Selling a single, liquid, ~35 DTE, ~0.30 delta call against it.
3. It then calculates the P&L for both legs of the trade to verify the core logic before running a full-scale, monthly-rolling backtest.

**PMCC Test Results (2023 Example):**
- **Long LEAPS**: GOOG $89.00 Call (Jan 2024 expiration) - Entry: $16.05 → Exit: $51.40 = **+$35.35 (+220.2%)**
- **Short Call**: GOOG $105.00 Call (Feb 2023 expiration) - Premium: $0.56 → Close: $0.01 = **+$0.55**
- **Total Strategy**: **$35.90** vs **$35.35** buy-and-hold (**+$0.55 additional income**)

## 4. Getting Started: A Step-by-Step Guide

This guide provides a complete process to set up and run the backtesting platform from a fresh clone.

### a. Prerequisites
1. **Python 3.11+**
2. **Java Development Kit (JDK)**
3. **`ThetaTerminalv3.jar`** file in the project's root directory.

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
# Core dependencies for ThetaData v3 API integration
pip3 install httpx numpy~=1.26.4 pandas>=2.3.0 pandas-ta>=0.3.14b python-dotenv>=1.0.1 thetadata==0.9.11 yfinance>=0.2.63 python-dateutil>=2.8.2 psutil
```

**Package Purposes:**
- `httpx` - **Primary HTTP client** for all ThetaData v3 API requests (CSV format parsing)
- `numpy` - Numerical computing foundation
- `pandas` - Data manipulation and analysis
- `pandas-ta` - Technical analysis indicators
- `python-dotenv` - Environment variable management
- `thetadata` - ThetaData API client library (legacy v2 support only)
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

### Core Components
* **`src/backtesting_engine/`**: The core Python package containing all logic for data handling, option selection, capital management, and trade execution.
* **`scripts/`**: Contains the runnable backtesting scripts, including `run_gemini_backtest.py`, `run_claude_backtest.py`, `run_strike_comparison_backtest.py`, and `run_simple_pmcc_test.py`.
* **`CLAUDE.md` / `GTC.md`**: Project documentation and planning files.
* **`ThetaTerminalv3.jar`**: The Java application required to connect to the ThetaData v3 API.

### ThetaData v3 API Integration
The platform has been **fully migrated to ThetaData v3 API** with the following modern architecture:

**Connection Management:**
- **Automatic ThetaTerminalv3 startup** with credentials file handling (`creds.txt`)
- **Port 25503** connectivity with v3 API endpoints (`/v3/*`)
- **Process detection and cleanup** with stale session handling
- **Comprehensive error reporting** and connection verification

**API Communication:**
- **Primary HTTP Client**: `httpx` library for all API requests (as per ThetaData documentation)
- **Response Format**: CSV parsing with `csv.reader()` (replaces legacy JSON)
- **Date Format**: YYYY-MM-DD format for all API parameters (converted from YYYYMMDD internally)
- **Endpoint Structure**: `http://localhost:25503/v3/[endpoint]` with proper parameter mapping

**Data Processing Pipeline:**
- **`api_call_csv()`**: Core function for CSV response parsing
- **`format_date_for_api()`**: Automatic date format conversion helper
- **Column Mapping**: Precise field extraction for EOD data, quotes, and Greeks
- **Caching**: Historical trading days cached in `market_days_cache.json`

### Advanced Features

**MCP (Model Context Protocol) Server Discovery:**
- **Endpoint**: `http://localhost:25503/mcp/sse` (Server-Sent Events)
- **Status**: Beta/experimental feature from ThetaData
- **Protocol**: JSON-RPC 2.0 over HTTP+SSE transport
- **Purpose**: AI agent integration capabilities (early development)

**Data Quality & Precision:**
- **Precise Entry Timing**: 10:00 AM ET price extraction for realistic backtests
- **Greeks Integration**: Delta, theta, vega, gamma, and IV data for strategy analysis
- **Split Handling**: Automatic adjustment for stock splits (e.g., GOOG 20:1 split in 2022)
- **Liquidity Filtering**: Volume-based filtering for realistic option selection

## 6. API Usage Guidelines

### Critical Implementation Requirements

**ThetaData v3 API Specifications:**
1. **HTTP Client**: Use `httpx` exclusively (as documented). Never use `curl` or `requests`.
2. **Response Format**: All endpoints return CSV data by default. Parse with `csv.reader()`.
3. **Date Format**: All date parameters must be in YYYY-MM-DD format.
4. **Base URL**: `http://localhost:25503/v3/[endpoint]`
5. **Headers**: No special headers required for most endpoints.

**Parameter Requirements:**
- **EOD Data**: `symbol`, `expiration`, `start_date`, `end_date`
- **At-Time Quotes**: `symbol`, `expiration`, `start_date`, `end_date`, `time_of_day` (HH:MM:SS.mmm)
- **Greeks**: `symbol`, `expiration`, `start_date`, `end_date`

**Data Format Examples:**
```python
# Correct v3 API call pattern
import httpx
import csv

url = "http://localhost:25503/v3/option/history/eod"
params = {
    "symbol": "GOOG",
    "expiration": "2024-01-19",  # YYYY-MM-DD format
    "start_date": "2023-01-03",  # YYYY-MM-DD format
    "end_date": "2023-01-03"
}

with httpx.Client(timeout=60) as client:
    response = client.get(url, params=params)
    response.raise_for_status()
    
    # Parse CSV response
    csv_reader = csv.reader(response.text.split("\n"))
    for row in csv_reader:
        if row:  # Process non-empty rows
            print(row)
```

**When implementing or modifying API calls:**
1. Consult the ThetaData v3 documentation for the specific endpoint
2. Follow the **exact parameter names and formats** from documentation examples
3. Use the `format_date_for_api()` helper for date conversion
4. Use `api_call_csv()` for standard CSV response parsing
5. Test with known working examples before implementing complex logic

## 7. Testing and Validation

The platform includes comprehensive testing capabilities:

**PMCC Strategy Validation:**
- Single-year focused testing with `run_simple_pmcc_test.py`
- Real historical data with precise entry/exit timing
- Greeks-based option selection (delta targeting)
- Volume-based liquidity filtering

**Performance Metrics:**
- Precise P&L calculations with commission considerations
- Greeks analysis (entry/exit delta, IV changes)
- Hold period tracking and annualized returns
- Strategy comparison (buy-and-hold vs enhanced strategies)

**Data Quality Assurance:**
- Multiple expiration testing with fallback logic
- Split-adjusted calculations for historical accuracy
- Market hours validation and trading day verification
- API error handling with detailed logging

The platform is production-ready for comprehensive LEAPS and PMCC strategy analysis with institutional-grade data accuracy and processing capabilities.
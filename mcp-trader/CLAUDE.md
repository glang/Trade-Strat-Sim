# LEAPS Options Backtesting System - Complete Guide

## Project Overview
This is a comprehensive **January LEAPS (Long-term Equity Anticipation Securities) backtesting system** that analyzes buying GOOG call options with ~15-month expiration on the first trading day of each year and selling them on the last trading day. The system uses ThetaData for both options data and market days detection, plus Tiingo for stock price verification, achieving realistic, historically-accurate backtesting.

## 🎯 The Strategy Being Backtested

### **Core Strategy: Annual January LEAPS**
- **Symbol:** GOOG (Google/Alphabet)
- **Entry:** First trading day of each year at 10:00 AM EST
- **Exit:** Last trading day of the same year at close
- **Option Type:** Call options (bullish strategy)
- **Expiration:** January of the following year (~15 months out)
- **Strike Selection:** In-the-money (ITM), closest to stock price, multiple of $5
- **Time Period:** 2016-2025 (10 years of backtesting)

### **Why This Strategy?**
- **LEAPS** provide long-term leverage on stock appreciation
- **January expiration** gives maximum time value
- **ITM strikes** reduce time decay risk
- **Annual cycle** provides consistent entry/exit points
- **GOOG** is a liquid, high-volume underlying

## 🏗️ System Architecture

### **Data Sources & Why They Were Chosen**

#### **ThetaData (Primary Data Source) - Standard Tier**
- **Options Data:** Most comprehensive historical options data (8+ years)
- **Market Days:** Uses `list/dates/stock/trade` endpoint for accurate trading days
- **Coverage:** 2015+ historical options data with intraday granularity
- **Subscription:** Options-only access ($49/month vs $199/month full access)
- **API Integration:** HTTP REST API via ThetaTerminal (localhost:25510)
- **Auto-Start:** Automatic ThetaTerminal health check and startup integration

#### **Tiingo (Stock Price Verification) - Paid Tier**
- **Purpose:** Stock price verification and entry day validation
- **Coverage:** Full historical stock data for major symbols
- **Cost:** Paid subscription (generous rate limits)
- **API Integration:** Direct HTTP API calls with authentication token

### **Market Days Detection Strategy**
- **Primary Method:** ThetaData `list/dates/stock/trade` endpoint
- **Why This Approach:** Returns actual trading days where GOOG was traded
- **Caching Strategy:** Permanent cache since historical trading days never change
- **Performance:** Instant lookups after initial fetch (0.008s vs API calls)

## 🔧 Technical Implementation

### **System Setup**

#### **1. ThetaTerminal Configuration (Auto-Start Enabled)**
```bash
# ThetaTerminal starts automatically when running backtests
# Manual start (if needed):
./start_theta.sh

# Verify connection
curl -s "http://localhost:25510/v2/system/mdds/status"
# Expected response: "CONNECTED"

# Health check endpoint used by auto-start system
curl -s "http://localhost:25510/v2/list/expirations?root=GOOG"
```

#### **2. Environment Configuration**
```bash
# Required in .env file (now located in the project root: ~/trade-strat-sim/.env)
THETADATA_PASSWORD=your_password_here
TIINGO_API_KEY=your_api_key_here
```

### **Core Algorithm Components**

#### **0. ThetaTerminal Health Check & Auto-Start System**
```python
def ensure_theta_terminal_running():
    """Check if ThetaTerminal is running, start if needed"""
    # Step 1: Quick health check
    response = requests.get("http://127.0.0.1:25510/v2/system/mdds/status", timeout=5)
    if response.text == "CONNECTED":
        return True
    
    # Step 2: Start ThetaTerminal in background
    subprocess.Popen(["./start_theta.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Step 3: Wait for connection with 30-second timeout
    for i in range(30):
        response = requests.get("http://127.0.0.1:25510/v2/system/mdds/status", timeout=2)
        if response.text == "CONNECTED":
            return True
        time.sleep(1)
    
    return False
```

**Auto-Start Implementation Logic:**
- **Health Check Endpoint:** `/v2/system/mdds/status` returns "CONNECTED" when ready
- **Background Launch:** Uses `subprocess.Popen()` to avoid 2-minute timeout issues
- **Controlled Waiting:** 30-second timeout with progress updates every 5 seconds
- **Integrated Calls:** Called automatically at the start of each backtest
- **Fallback Support:** Manual `./start_theta.sh` if auto-start fails

#### **1. Market Day Detection (ThetaData-Based)**
```python
def get_first_trading_day_of_year(symbol: str, year: int) -> str:
    """Get first trading day using ThetaData market days cache"""
    # Uses: ThetaData list/dates/stock/trade endpoint
    # Caches: All trading days permanently 
    # Returns: YYYYMMDD format date string
```

**New Implementation Logic:**
- **ThetaData Endpoint:** `curl -s "http://127.0.0.1:25510/v2/list/dates/stock/trade?root=GOOG&use_csv=true"`
- **CSV Parsing:** Extracts trading days from CSV response
- **Permanent Caching:** Historical trading days cached in `market_days_cache.json`
- **Instant Lookups:** Subsequent calls use cached data (0.008s performance)

#### **2. LEAPS Discovery Process**
```python
def find_optimal_leaps_accurate_optimized(symbol: str, year: int, entry_date: str, exit_date: str, stock_price: float):
    """Multi-step LEAPS discovery with optimization"""
    # Step 1: Get all available expirations
    # Step 2: Filter for January of following year
    # Step 3: Test each expiration sequentially for data validity
    # Step 4: Use BULK EOD API for 7x speed improvement
    # Step 5: Filter ITM strikes (multiples of 5)
    # Step 6: Validate data quality with bulk at-time quotes
    # Step 7: Test entry/exit pricing
```

**Why This Approach:**
- **Accuracy First:** Tests ALL January expirations for complete data
- **Sequential Testing:** Finds first valid expiration (same as complete_smart_leaps.py)
- **Bulk API:** 7x faster than individual strike testing
- **ITM Filter:** Reduces time decay risk
- **Data Validation:** Prevents bad data from affecting results

#### **3. Price Extraction Logic**

**Entry Pricing (10:00 AM EST):**
```python
def extract_precise_entry_price_from_bulk(bulk_quotes, target_strike):
    """Extract realistic entry price from bulk quote data"""
    target_time_ms = 36000000  # 10:00 AM EST
    # Find exact strike match in bulk quotes
    # Return ASK price (buying the option)
```

**Exit Pricing (End of Day):**
```python
def get_exit_price_individual(symbol, exp_date, exit_strike, exit_date):
    """Extract realistic exit price from EOD data"""
    # Priority: Close price > Bid price > $0.00 (worthless)
    # Return BID price (selling the option)
    # Accept $0.00 as valid (worthless option)
```

**Why These Pricing Rules:**
- **10:00 AM Entry:** Avoids market open volatility, ensures liquidity
- **Ask for Entry:** Realistic cost of buying
- **Bid for Exit:** Realistic proceeds from selling
- **$0.00 Acceptance:** Worthless options are valid outcomes

#### **3a. Current Year Exit Date Handling**
```python
def analyze_year_accurate_optimized(year: int):
    """Handle exit dates for current vs completed years"""
    current_year = datetime.now().year
    if year == current_year:
        # Use most recent trading day with available data
        exit_date = get_most_recent_trading_day("GOOG")
    else:
        # Use last trading day of completed year
        exit_date = get_last_trading_day_of_year("GOOG", year)
```

**Dynamic Exit Date Logic:**
- **Past Years:** Use December 31 (or last trading day of year)
- **Current Year:** Use most recent available trading day (handles EOD data delay)
- **Real-Time Updates:** Automatically reflects new data as it becomes available
- **Data Validation:** Ensures exit prices exist before attempting analysis

#### **4. Stock Split Handling**
```python
def detect_stock_split(symbol: str, entry_date: str, exit_date: str) -> dict:
    """Detect and handle stock splits during holding period"""
    # Known: GOOG 20:1 split on July 15, 2022
    # Impact: $2,850 strike becomes $142.50 equivalent
    # Method: Date-based detection with ratio calculation
```

**Why This Matters:**
- **GOOG Split:** July 15, 2022 (20:1 ratio)
- **Strike Adjustment:** Original strikes become 1/20th the value
- **Contract Continuity:** Same expiration, adjusted strike
- **Data Integrity:** Ensures pre/post-split data consistency

### **Performance Optimizations**

#### **1. ThetaData Market Days Cache**
- **Problem:** Repeated API calls for first/last trading days
- **Solution:** One-time fetch with permanent caching
- **Result:** Instant lookups (0.008s) after initial cache population
- **Implementation:** `market_days_cache.py` with CSV parsing

#### **2. Bulk EOD API Usage**
- **Problem:** Individual strike testing = 20+ API calls per year
- **Solution:** Single bulk call gets all strikes for expiration
- **Result:** 7x speed improvement (0.63s vs 4.45s per year)
- **Implementation:** In-memory filtering after bulk data retrieval

#### **3. Sequential Expiration Testing**
- **Problem:** Strategic expiration selection caused accuracy issues
- **Solution:** Test ALL January expirations until valid data found
- **Result:** 90% success rate vs 80% with strategic selection
- **Implementation:** Same logic as `complete_smart_leaps.py`

## 📊 Key Files & Their Purposes

### **Main Implementation Files**

#### **`accurate_optimized_leaps.py`** - Current Production Version
- **Purpose:** Accurate LEAPS backtest with ThetaData market days cache
- **Features:** Full expiration testing, bulk API, ThetaData market days, split handling, auto-start
- **Performance:** ~5 API calls per year, 90%+ success rate
- **Auto-Start:** Automatically checks and starts ThetaTerminal if needed
- **Usage:** Primary backtesting script with all optimizations

#### **`market_days_cache.py`** - Market Days Cache System
- **Purpose:** ThetaData-based market days detection and caching
- **Features:** CSV parsing, permanent caching, instant lookups
- **Performance:** 0.008s cached lookups vs API calls
- **Usage:** Imported by all backtesting scripts

#### **Previous Optimization Attempts:**
- **`ultimate_two_call_leaps.py`** - 2 API call optimization (sacrificed accuracy)
- **`complete_smart_leaps.py`** - Original accurate implementation (slow)
- **`fixed_bulk_eod_leaps.py`** - Bulk EOD optimization (Tiingo-based market days)

### **Supporting Files**

#### **`start_theta.sh`** - ThetaTerminal Startup Script
- **Purpose:** Automated ThetaTerminal startup with credentials
- **Usage:** Called automatically by backtests, or manually `./start_theta.sh`
- **Auto-Integration:** Used by `ensure_theta_terminal_running()` function

#### **`.env`** - Environment Configuration
- **Contents:** ThetaData password, Tiingo API key
- **Security:** Not committed to version control

#### **Cache Files**
- **`market_days_cache.json`** - ThetaData trading days (permanent)
- **`smart_stock_cache.json`** - Tiingo stock prices (with expiration)

## 🎯 API Usage Patterns & Why They Work

### **ThetaData API Strategy**

#### **1. Market Days Detection - New Primary Method**
```bash
# Get all trading days for GOOG
curl -s "http://127.0.0.1:25510/v2/list/dates/stock/trade?root=GOOG&use_csv=true"
```
**Why:** Authoritative source for actual trading days, permanent caching

#### **2. Discovery Phase - List Endpoints**
```bash
# Get all expirations
curl -s "http://localhost:25510/v2/list/expirations?root=GOOG"
```
**Why:** Validates data existence before processing

#### **3. Bulk Data Retrieval - Performance Critical**
```bash
# Bulk EOD - All contracts for expiration
curl -s "http://localhost:25510/v2/bulk_hist/option/eod?root=GOOG&exp=20240119&start_date=20230102&end_date=20230102"
```
**Why:** 7x faster than individual calls, comprehensive data

#### **4. Precise Entry Pricing - Bulk Quote Data**
```bash
# Bulk at-time quotes for all strikes
curl -s "http://localhost:25510/v2/bulk_at_time/option/quote?root=GOOG&exp=20240119&start_date=20230102&end_date=20230102&ivl=36000000&rth=true"
```
**Why:** Realistic bid/ask pricing, 10:00 AM timestamp precision

#### **5. Exit Pricing - Individual EOD Data**
```bash
# End-of-day data for specific strike
curl -s "http://localhost:25510/v2/hist/option/eod?root=GOOG&exp=20240119&strike=170000&right=C&start_date=20231230&end_date=20231230"
```
**Why:** Official closing prices, bid availability for illiquid options

### **Tiingo API Strategy (Verification Only)**

#### **Stock Price Verification**
```bash
# Daily stock data for entry day
curl -s "https://api.tiingo.com/tiingo/daily/GOOG/prices?startDate=2023-01-02&endDate=2023-01-02&token=API_KEY"
```
**Why:** Confirms market open, provides entry reference price

### **Critical Data Format Requirements**

#### **Strike Prices: Millidollar Format**
- **ThetaData Format:** 170000 = $170.00
- **Conversion:** Dollar amount × 1000
- **Examples:** $67.50 = 67500, $142.50 = 142500

#### **Dates: YYYYMMDD Format**
- **ThetaData Format:** 20230102 = January 2, 2023
- **No Separators:** Hyphens or slashes break the API
- **Validation:** datetime.strptime('%Y%m%d') for parsing

#### **Options Rights**
- **Calls:** 'C' (used for LEAPS strategy)
- **Puts:** 'P' (not used in this strategy)

## 🔍 Common Issues & Solutions

### **1. ThetaTerminal Auto-Start System**
**Features:** Automatic health check and startup
**Health Check:** Tests `/v2/system/mdds/status` endpoint for "CONNECTED" response
**Auto-Start:** Launches ThetaTerminal in background with 30-second timeout
**Manual Override:** `./start_theta.sh` if auto-start fails

**Troubleshooting Auto-Start:**
```bash
# Check if ThetaTerminal is running
ps aux | grep theta

# Test health check manually
curl -s "http://localhost:25510/v2/system/mdds/status"

# View auto-start function output for debugging
python3 -c "from accurate_optimized_leaps import ensure_theta_terminal_running; ensure_theta_terminal_running()"
```

### **2. Market Days Cache Missing**
**Symptoms:** No cached trading days found
**Solution:** 
```bash
python3 market_days_cache.py  # Populate cache
```

### **3. Stock Split Tracking**
**Symptoms:** No exit data found, wrong strike prices
**Solution:** `detect_stock_split()` with strike adjustment logic

### **4. Zero-Value Options**
**Symptoms:** $0.00 prices rejected as invalid
**Solution:** Accept $0.00 as legitimate worthless option value



## 📈 Backtest Results & Performance

### **Complete 10-Year Analysis (2016-2025)**
- **Total Years Tested:** 10 (2016-2025)
- **Data Availability:** 100% (10/10 years with complete data)
- **Win Rate:** 60% (6/10 years profitable)
- **Average Winner:** +212.5% return
- **Average Loser:** -73.3% return
- **Current Year Status:** 2025 (partial, down -58.3% through July 9)

### **Performance Metrics**
- **Market Days Lookup:** 0.008s (cached) vs API calls
- **Average Discovery Time:** ~2.0 seconds per year
- **API Calls Per Year:** ~5 (vs 12+ in original implementation)
- **Total Execution Time:** ~20 seconds (all 10 years)

### **Detailed 10-Year LEAPS Performance**
| Year | Entry | Stock Price | Strike | Entry Price | Exit Price | Return | Status |
|------|-------|-------------|--------|-------------|------------|--------|--------|
| 2016 | Jan 4 | $743.00 | $740 | $87.50 | $35.20 | **-59.8%** | Loss |
| 2017 | Jan 3 | $778.81 | $770 | $88.40 | $274.60 | **+210.6%** | Win |
| 2018 | Jan 2 | $1,048.34 | $1,040 | $110.40 | $27.50 | **-75.1%** | Loss |
| 2019 | Jan 2 | $1,016.57 | $1,015 | $137.80 | $320.30 | **+132.4%** | Win |
| 2020 | Jan 2 | $1,341.55 | $1,340 | $150.20 | $409.00 | **+172.3%** | Win |
| 2021 | Jan 4 | $1,757.54 | $1,740 | $230.40 | $1,147.80 | **+398.2%** | Win |
| 2022 | Jan 3 | $2,889.51 | $2,850→$142.50* | $360.50 | $0.00 | **-100.0%** | Loss |
| 2023 | Jan 3 | $89.83 | $89 | $16.05 | $51.40 | **+220.2%** | Win |
| 2024 | Jan 2 | $139.60 | $135 | $21.95 | $53.50 | **+143.7%** | Win |
| 2025 | Jan 2 | $191.49 | $190 | $28.90 | $12.05** | **-58.3%** | Open |

*Strike adjusted for GOOG 20:1 stock split (July 15, 2022)  
**Current position as of July 9, 2025

### **Key Performance Highlights**

#### **Best Performing Years**
- **2021:** +398.2% return (GOOG $1,757 → $1,740 call: $230.40 → $1,147.80)
- **2023:** +220.2% return (GOOG $89.83 → $89 call: $16.05 → $51.40)
- **2017:** +210.6% return (GOOG $778.81 → $770 call: $88.40 → $274.60)

#### **Worst Performing Years**
- **2022:** -100.0% return (GOOG stock split impact, option expired worthless)
- **2018:** -75.1% return (Bear market impact)
- **2016:** -59.8% return (Market volatility)

#### **Current Year (2025)**
- **Status:** Open position (187 days held, 190 days remaining)
- **Performance:** Down -58.3% ($28.90 → $12.05 as of July 9)
- **Auto-Update:** Position value updates with most recent trading day data

## 🚀 Getting Started: A Guide for New Agents

This guide provides everything a new AI agent needs to set up and run this backtesting project from a fresh clone of the repository.

### **1. Environment Setup**

**a. Create the Environment File:**

This project requires API keys and credentials, which are stored in a `.env` file. A template is provided in the repository.

1.  Navigate to the `mcp-trader` directory.
2.  Copy the example environment file:

    ```bash
    cp .env.example .env
    ```

3.  **Edit the `.env` file** and add your credentials:

    ```
    THETADATA_PASSWORD=your_theatadata_password_here
    TIINGO_API_KEY=your_tiingo_api_key_here
    ```

**b. Install Dependencies:**

The project uses `uv` to manage Python packages. All required libraries are listed in the `pyproject.toml` file.

1.  Ensure `uv` is installed. If not, you can typically install it with `pip`:

    ```bash
    pip install uv
    ```

2.  From the `mcp-trader` directory, create a virtual environment and install the dependencies:

    ```bash
    uv venv
    uv pip install -r requirements.txt
    ```

**c. Set Executable Permissions:**

The script that automatically starts the ThetaData terminal needs to be executable.

1.  From the `mcp-trader` directory, grant execute permissions to the `start_theta.sh` script:

    ```bash
    chmod +x start_theta.sh
    ```

### **2. How to Run a Complete Backtest**

With the environment now fully configured, you can run the backtest. The process is designed to be highly automated.

**a. System Startup (Auto-Start Enabled)**

There is no need to start the ThetaTerminal manually. The backtesting script will automatically check if it's running and start it if necessary.

*   **Optional:** To verify the connection manually after the script has started, you can use this command:

    ```bash
    curl -s "http://localhost:25510/v2/system/mdds/status"
    ```

**b. Initialize Market Days Cache (One-Time Setup)**

The first time you run the backtest, you must populate the market days cache. This is a one-time operation, as historical market data does not change.

*   Run the following command from the `mcp-trader` directory:

    ```bash
    python3 market_days_cache.py
    ```

    You should see output indicating that thousands of trading days have been cached.

**c. Execute the Backtest**

You are now ready to run the main backtesting script.

*   From the `mcp-trader` directory, execute the following command:

    ```bash
    python3 accurate_optimized_leaps.py
    ```

*   **Expected Output:** The script will first check for ThetaTerminal and start it if needed. It will then proceed to analyze each year from 2016 to the present, running both the Annual and Quarterly strategies. Finally, it will display a detailed, side-by-side comparison of the results.

### **3. Results Interpretation**

The final output will be a table comparing the two primary strategies:

*   **Annual Strategy:** A simple buy-and-hold approach.
*   **Quarterly Rolling Strategy:** A more active strategy that rolls the LEAP option every quarter.

The table will include the total return, a breakdown of winning vs. losing trades, and key Greek metrics (like Delta and IV) to provide deeper insight into the performance of each strategy.

## 🔧 Extending the System

### **Adding New Symbols**
1. Verify ThetaData coverage: `curl -s "http://localhost:25510/v2/list/expirations?root=SYMBOL"`
2. Populate market days cache: Update `market_days_cache.py` for new symbol
3. Ensure Tiingo stock data: `curl -s "https://api.tiingo.com/tiingo/daily/SYMBOL/prices?..."`
4. Update split detection logic if needed

### **Modifying Strategy Parameters**
- **Entry Time:** Change `target_time_ms` in bulk quote calls
- **Strike Selection:** Modify ITM filtering logic
- **Exit Timing:** Update market days cache usage
- **Expiration Targeting:** Change January filtering in discovery

### **Performance Enhancements**
- **Parallel Processing:** Process multiple years concurrently
- **Extended Caching:** Cache more intermediate results
- **Batch API Calls:** Combine multiple bulk requests
- **Data Validation:** Pre-filter unreliable data sources

## 🎯 Key Success Factors

### **1. Accurate Market Days**
- Use ThetaData authoritative trading days
- Permanent caching for historical consistency
- Instant lookups for performance

### **2. Realistic Pricing**
- Use bid/ask spreads, not theoretical midpoints
- Account for market impact and slippage
- Validate liquidity before assuming fills

### **3. Data Quality**
- Test ALL January expirations for completeness
- Handle corporate actions (splits, dividends)
- Filter out illiquid options (wide spreads)

### **4. System Robustness**
- Graceful handling of missing data
- Fallback mechanisms for API failures
- Comprehensive error logging

### **5. Performance Optimization**
- ThetaData market days cache system
- Bulk API usage over individual calls
- In-memory processing of large datasets
- Efficient filtering and sorting algorithms
- Automated ThetaTerminal management

## 🏆 Current System Status

The LEAPS backtesting system now features:

### ✅ **Completed Optimizations**
- **ThetaData Market Days Cache:** Authoritative trading days with permanent caching
- **Accurate Sequential Testing:** Tests all January expirations for complete data
- **Bulk API Integration:** 7x performance improvement with bulk EOD/quote calls
- **Stock Split Handling:** Proper GOOG 20:1 split adjustment
- **Comprehensive Error Handling:** Graceful degradation and detailed logging
- **Auto-Start Integration:** Automatic ThetaTerminal health check and startup
- **Dynamic Year Range:** Automatically tests 2016 through current year
- **Current Year Handling:** Uses most recent available trading day for ongoing positions

### 🎯 **Performance Achievements**
- **API Efficiency:** ~4.7 calls per year (down from 12+)
- **Data Availability:** 100% (10/10 years with complete results)
- **Cache Performance:** 0.008s lookups vs API calls
- **Total Runtime:** ~20 seconds for 10-year backtest
- **Real-Time Updates:** Automatically includes current year performance through most recent trading day

This backtesting system provides a comprehensive, realistic analysis of the January LEAPS strategy with production-quality implementation and optimization. The combination of ThetaData's comprehensive options data and market days detection creates the most accurate historical simulation possible of real trading conditions.
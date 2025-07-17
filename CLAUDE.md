# LEAPS Trading Strategy Project - Current Status

## Project Overview
This project implements and backtests LEAPS (Long-term Equity Anticipation Securities) trading strategies for GOOG, focusing on compounding capital management approaches.

## Current Implementation Status

### Main Files
- **`claude_compounding_leaps_backtest.py`** - Primary implementation with two compounding strategies
- **`accurate_optimized_leaps.py`** - Core LEAPS analysis functions and data retrieval
- **`smart_leaps_backtest.py`** - Stock price verification and caching system
- **`market_days_cache.py`** - ThetaData-based market days detection and caching
- **`GTC.md`** - Implementation plan for compounding strategies

### Implemented Strategies

#### 1. Compounding Annual Strategy
- Single January LEAPS trade per year using full available capital
- Entry: First trading day of year
- Exit: Last trading day of year (or most recent for current year)
- Position sizing: Uses 95% of available capital with realistic constraints

#### 2. Compounding Quarterly Strategy  
- Rolling 15-month LEAPS positions every quarter
- Capital compounds with each trade (wins/losses carry to next quarter)
- Four trades per year with position sizing based on available capital

### Key Features
- **Real position sizing** based on available capital and option prices
- **Transaction costs**: $0.35 commission per contract
- **Liquidity constraints**: Maximum 500 contracts per trade
- **Capital utilization**: Targets 95% of available capital
- **Error handling**: Graceful handling of missing data and API failures
- **Performance optimization**: Quiet mode to suppress verbose output

### System Requirements
- **ThetaData subscription** (Options-only tier sufficient)
- **Tiingo API key** for stock price verification
- **Python 3.11+** with required dependencies
- **Environment file**: `.env` in project root with API credentials

### Dependencies
- `python-dateutil` - Date calculations and relative deltas
- `requests` - API calls
- `numpy`, `pandas` - Data processing
- Other dependencies listed in `pyproject.toml`

### Current Configuration
- **Starting capital**: $100,000 per year (resets annually for clean comparison)
- **Symbol**: GOOG
- **Backtest period**: 2016-2025
- **Commission**: $0.35 per contract
- **Max contracts**: 500 per trade
- **Capital utilization**: 95%

### Data Sources
- **ThetaData**: Options data, market days, bulk EOD/quote data
- **Tiingo**: Stock price verification and entry day validation
- **Auto-start**: ThetaTerminal health check and automatic startup

### Setup Commands
```bash
# Navigate to project
cd ~/trade-strat-sim/mcp-trader

# Install dependencies (if needed)
uv pip install python-dateutil

# Start ThetaTerminal (if not auto-started)
./start_theta.sh

# Run backtest
python3 claude_compounding_leaps_backtest.py --start-year 2016 --end-year 2025
```

### Next Steps
- Complete full 2016-2025 backtest run for final performance comparison
- Compare results with Gemini's implementation
- Document final performance metrics and insights

### Performance Notes
- Initial implementation had stdout redirection bottleneck (resolved)
- Current implementation uses quiet flags for better performance
- Underlying imported functions may still produce verbose ThetaData API logging
- Expected runtime: Several minutes for full 10-year backtest

### Recent Changes
- Updated commission from $0.65 to $0.35 per contract
- Replaced inefficient stdout redirection with quiet flag approach
- Optimized performance based on Gemini feedback
- All changes committed and pushed to GitHub
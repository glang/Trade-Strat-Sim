
from src.backtesting_engine.market_days_cache import get_last_trading_day_of_year

last_day = get_last_trading_day_of_year("GOOG", 2023)
print(last_day)

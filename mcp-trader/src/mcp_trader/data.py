import os
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import pandas as pd
from dotenv import load_dotenv

try:
    from fastmcp import FastMCP
    USE_FASTMCP = True
except ImportError:
    USE_FASTMCP = False

try:
    from thetadata import ThetaClient, OptionReqType, DateRange
    THETADATA_AVAILABLE = True
except ImportError:
    THETADATA_AVAILABLE = False

load_dotenv()

# Initialize FastMCP if available
if USE_FASTMCP:
    mcp = FastMCP("mcp-trader-resources")


class MarketData:
    """Handles all market data fetching operations."""

    def __init__(self):
        # Initialize Tiingo
        self.api_key = os.getenv("TIINGO_API_KEY")
        if not self.api_key:
            raise ValueError("TIINGO_API_KEY not found in environment")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {self.api_key}",
        }
        
        # Initialize ThetaData client if available
        self.theta_client = None
        if THETADATA_AVAILABLE:
            try:
                username = os.getenv("THETADATA_USERNAME", "default")
                password = os.getenv("THETADATA_PASSWORD", "default")
                # Strip quotes from password if present
                if password.startswith('"') and password.endswith('"'):
                    password = password[1:-1]
                self.theta_client = ThetaClient(username=username, passwd=password)
            except Exception as e:
                print(f"Warning: Could not initialize ThetaData client: {e}")
                self.theta_client = None

    async def get_crypto_historical_data(
        self,
        symbol: str,
        lookback_days: int = 365,
        provider: str = "tiingo",
        quote_currency: str = "usd",
    ) -> pd.DataFrame:
        """
        Fetch historical daily data for a given crypto asset.

        Args:
            symbol (str): The crypto symbol (e.g., 'BTC', 'ETH', or 'BTCUSDT' for Binance).
            lookback_days (int): Number of days to look back from today.
            provider (str): 'tiingo' or 'binance'.
            quote_currency (str): Quote currency (default 'usd' for Tiingo, 'USDT' for Binance).

        Returns:
            pd.DataFrame: DataFrame containing historical crypto market data.

        Raises:
            ValueError: If the symbol is invalid or no data is returned.
            Exception: For other unexpected issues during the fetch operation.
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)

        if provider.lower() == "tiingo":
            # Tiingo expects symbols like 'btcusd'
            pair = f"{symbol.lower()}{quote_currency.lower()}"
            url = (
                f"https://api.tiingo.com/tiingo/crypto/prices?"
                f"tickers={pair}&"
                f"startDate={start_date.strftime('%Y-%m-%d')}&"
                f"endDate={end_date.strftime('%Y-%m-%d')}&"
                f"resampleFreq=1day"
            )
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 404:
                            raise ValueError(f"Crypto symbol not found: {symbol}")
                        response.raise_for_status()
                        data = await response.json()

                if not data or not data[0].get("priceData"):
                    raise ValueError(f"No data returned for {symbol} on Tiingo")

                df = pd.DataFrame(data[0]["priceData"])
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                df["open"] = df["open"].astype(float)
                df["high"] = df["high"].astype(float)
                df["low"] = df["low"].astype(float)
                df["close"] = df["close"].astype(float)
                df["volume"] = df["volume"].astype(float)
                df["symbol"] = pair.upper()
                return df

            except aiohttp.ClientError as e:
                raise ConnectionError(
                    f"Network error while fetching crypto data for {symbol} (Tiingo): {e}"
                ) from e
            except ValueError as ve:
                raise ve
            except Exception as e:
                raise Exception(
                    f"Unexpected error fetching crypto data for {symbol} (Tiingo): {e}"
                ) from e

        elif provider.lower() == "binance":
            # Binance expects symbols like 'BTCUSDT'
            binance_symbol = symbol.upper()
            interval = "1d"
            limit = min(lookback_days, 1000)  # Binance max 1000
            url = (
                f"https://api.binance.com/api/v3/klines?"
                f"symbol={binance_symbol}&interval={interval}&limit={limit}"
            )
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    async with session.get(url) as response:
                        if response.status == 404:
                            raise ValueError(f"Crypto symbol not found: {symbol}")
                        response.raise_for_status()
                        data = await response.json()

                if not data:
                    raise ValueError(f"No data returned for {symbol} on Binance")

                # Binance kline columns:
                # 0: open time, 1: open, 2: high, 3: low, 4: close, 5: volume, 6: close time, ...
                df = pd.DataFrame(
                    data,
                    columns=[
                        "open_time",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "close_time",
                        "quote_asset_volume",
                        "number_of_trades",
                        "taker_buy_base_asset_volume",
                        "taker_buy_quote_asset_volume",
                        "ignore",
                    ],
                )
                df["date"] = pd.to_datetime(df["open_time"], unit="ms")
                df.set_index("date", inplace=True)
                df["open"] = df["open"].astype(float)
                df["high"] = df["high"].astype(float)
                df["low"] = df["low"].astype(float)
                df["close"] = df["close"].astype(float)
                df["volume"] = df["volume"].astype(float)
                df["symbol"] = binance_symbol
                return df[["open", "high", "low", "close", "volume", "symbol"]]

            except aiohttp.ClientError as e:
                raise ConnectionError(
                    f"Network error while fetching crypto data for {symbol} (Binance): {e}"
                ) from e
            except ValueError as ve:
                raise ve
            except Exception as e:
                raise Exception(
                    f"Unexpected error fetching crypto data for {symbol} (Binance): {e}"
                ) from e

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def get_historical_data(self, symbol: str, lookback_days: int = 365) -> pd.DataFrame:
        """
        Fetch historical daily data for a given symbol.

        Args:
            symbol (str): The stock symbol to fetch data for.
            lookback_days (int): Number of days to look back from today.

        Returns:
            pd.DataFrame: DataFrame containing historical market data.

        Raises:
            ValueError: If the symbol is invalid or no data is returned.
            Exception: For other unexpected issues during the fetch operation.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        url = (
            f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?"
            f"startDate={start_date.strftime('%Y-%m-%d')}&"
            f"endDate={end_date.strftime('%Y-%m-%d')}"
        )

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 404:
                        raise ValueError(f"Symbol not found: {symbol}")
                    response.raise_for_status()
                    data = await response.json()

            if not data:
                raise ValueError(f"No data returned for {symbol}")

            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)

            df[["open", "high", "low", "close"]] = df[
                ["adjOpen", "adjHigh", "adjLow", "adjClose"]
            ].round(2)
            df["volume"] = df["adjVolume"].astype(int)
            df["symbol"] = symbol.upper()

            return df

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Network error while fetching data for {symbol}: {e}") from e
        except ValueError as ve:
            raise ve  # Propagate value errors (symbol issues, no data, etc.)
        except Exception as e:
            raise Exception(f"Unexpected error fetching data for {symbol}: {e}") from e

    async def get_options_chain(
        self, 
        symbol: str, 
        expiration: str = None, 
        min_delta: float = None,
        max_delta: float = None
    ) -> pd.DataFrame:
        """
        Fetch options chain data from ThetaData.
        
        Args:
            symbol (str): The underlying symbol (e.g., 'AAPL')
            expiration (str): Expiration date in YYYY-MM-DD format (optional)
            min_delta (float): Minimum delta filter (optional)
            max_delta (float): Maximum delta filter (optional)
            
        Returns:
            pd.DataFrame: DataFrame containing options chain data
            
        Raises:
            ValueError: If ThetaData is not available or configured
            Exception: For other unexpected issues
        """
        if not self.theta_client:
            raise ValueError("ThetaData client not available. Please check configuration.")
        
        try:
            # If no expiration provided, get the nearest one
            if not expiration:
                expirations = self.theta_client.get_expirations(symbol)
                if not expirations:
                    raise ValueError(f"No options expirations found for {symbol}")
                expiration = expirations[0]  # Use nearest expiration
            
            # Convert expiration string to datetime if needed
            if isinstance(expiration, str):
                exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            else:
                exp_date = expiration
                
            # Get options chain - use get_strikes to get available strikes first
            strikes = self.theta_client.get_strikes(symbol, exp_date.strftime("%Y%m%d"))
            
            if not strikes:
                raise ValueError(f"No strikes found for {symbol} expiration {expiration}")
            
            # Get option data for all strikes (calls and puts)
            chain_data_list = []
            date_range = DateRange(datetime.now() - timedelta(days=5), datetime.now())
            
            # Sample a few strikes to avoid too many requests
            sample_strikes = strikes[::max(1, len(strikes)//10)]  # Sample every 10th strike
            
            for strike in sample_strikes:
                for right in ['C', 'P']:
                    try:
                        option_data = self.theta_client.get_hist_option(
                            req=OptionReqType.EOD,
                            root=symbol,
                            exp=exp_date.strftime("%Y%m%d"),
                            strike=int(strike * 1000),  # ThetaData uses 1/1000th
                            right=right,
                            date_range=date_range
                        )
                        if option_data is not None and not option_data.empty:
                            option_data['strike'] = strike
                            option_data['right'] = right
                            chain_data_list.append(option_data)
                    except Exception as e:
                        continue  # Skip failed requests
            
            # Combine all option data
            if chain_data_list:
                import pandas as pd
                chain_data = pd.concat(chain_data_list, ignore_index=True)
            else:
                chain_data = pd.DataFrame()
            
            # Convert to DataFrame if it's not already
            if not isinstance(chain_data, pd.DataFrame):
                chain_data = pd.DataFrame(chain_data)
            
            # Add useful columns for PMCC analysis
            if not chain_data.empty:
                chain_data['symbol'] = symbol.upper()
                chain_data['expiration'] = expiration
                
                # Filter by delta if specified
                if min_delta is not None and 'delta' in chain_data.columns:
                    chain_data = chain_data[chain_data['delta'] >= min_delta]
                if max_delta is not None and 'delta' in chain_data.columns:
                    chain_data = chain_data[chain_data['delta'] <= max_delta]
            
            return chain_data
            
        except Exception as e:
            raise Exception(f"Error fetching options chain for {symbol}: {e}") from e

    async def get_options_greeks(
        self, 
        symbol: str, 
        strike: float, 
        expiration: str, 
        option_type: str = "C"
    ) -> dict:
        """
        Get Greeks for a specific option contract.
        
        Args:
            symbol (str): The underlying symbol
            strike (float): Strike price
            expiration (str): Expiration date in YYYY-MM-DD format
            option_type (str): 'C' for call, 'P' for put
            
        Returns:
            dict: Dictionary containing Greeks data
        """
        if not self.theta_client:
            raise ValueError("ThetaData client not available. Please check configuration.")
        
        try:
            # Convert expiration to required format
            if isinstance(expiration, str):
                exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            else:
                exp_date = expiration
            
            # Get options data for the specific contract
            option_data = self.theta_client.get_hist_option(
                req=OptionReqType.EOD,
                root=symbol,
                exp=exp_date.strftime("%Y%m%d"),
                strike=int(strike * 1000),  # ThetaData uses strike in 1/1000th
                right=option_type,
                date_range=DateRange(datetime.now() - timedelta(days=1), datetime.now())
            )
            
            if isinstance(option_data, pd.DataFrame) and not option_data.empty:
                # Get the most recent data
                latest = option_data.iloc[-1]
                return {
                    'symbol': symbol,
                    'strike': strike,
                    'expiration': expiration,
                    'option_type': option_type,
                    'delta': latest.get('delta', None),
                    'gamma': latest.get('gamma', None),
                    'theta': latest.get('theta', None),
                    'vega': latest.get('vega', None),
                    'iv': latest.get('implied_volatility', None),
                    'bid': latest.get('bid', None),
                    'ask': latest.get('ask', None),
                    'last': latest.get('close', None),
                    'volume': latest.get('volume', None),
                    'open_interest': latest.get('open_interest', None)
                }
            else:
                return {
                    'error': f'No data found for {symbol} {strike} {option_type} {expiration}'
                }
                
        except Exception as e:
            return {
                'error': f'Error fetching Greeks for {symbol} {strike} {option_type} {expiration}: {e}'
            }

    def is_thetadata_available(self) -> bool:
        """Check if ThetaData client is available and configured."""
        return self.theta_client is not None


# FastMCP Resources Implementation
if USE_FASTMCP:
    # Create a global instance for the resources to use
    _market_data = MarketData()

    # Cache for resource data with TTL
    _resource_cache: dict[str, dict[str, Any]] = {}
    _cache_ttl = 300  # 5 minutes cache TTL

    def _is_cache_valid(cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in _resource_cache:
            return False
        cached = _resource_cache[cache_key]
        return (datetime.now() - cached["timestamp"]).total_seconds() < _cache_ttl

    @mcp.resource("stock://{symbol}")
    async def get_stock_price(symbol: str) -> dict[str, Any]:
        """
        Get current and recent stock price data.

        Returns the latest price, daily change, and key statistics for a stock symbol.
        """
        cache_key = f"stock:{symbol}"

        # Check cache first
        if _is_cache_valid(cache_key):
            return _resource_cache[cache_key]["data"]

        try:
            # Fetch last 5 days of data
            df = await _market_data.get_historical_data(symbol, lookback_days=5)

            latest = df.iloc[-1]
            prev_close = df.iloc[-2]["close"] if len(df) > 1 else latest["close"]

            data = {
                "symbol": symbol.upper(),
                "price": float(latest["close"]),
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "volume": int(latest["volume"]),
                "change": float(latest["close"] - prev_close),
                "change_percent": float((latest["close"] - prev_close) / prev_close * 100),
                "timestamp": datetime.now().isoformat(),
                "source": "tiingo",
            }

            # Cache the result
            _resource_cache[cache_key] = {"data": data, "timestamp": datetime.now()}

            return data

        except Exception as e:
            return {"error": str(e), "symbol": symbol, "timestamp": datetime.now().isoformat()}

    @mcp.resource("stock://{symbol}/history")
    async def get_stock_history(symbol: str, days: int | None = 30) -> dict[str, Any]:
        """
        Get historical stock price data.

        Returns OHLCV data for the specified number of days.
        """
        cache_key = f"stock:{symbol}:history:{days}"

        # Check cache first
        if _is_cache_valid(cache_key):
            return _resource_cache[cache_key]["data"]

        try:
            df = await _market_data.get_historical_data(symbol, lookback_days=days)

            # Convert DataFrame to list of dictionaries
            history = []
            for date, row in df.iterrows():
                history.append(
                    {
                        "date": date.isoformat(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )

            data = {
                "symbol": symbol.upper(),
                "days": days,
                "data": history,
                "timestamp": datetime.now().isoformat(),
                "source": "tiingo",
            }

            # Cache the result
            _resource_cache[cache_key] = {"data": data, "timestamp": datetime.now()}

            return data

        except Exception as e:
            return {"error": str(e), "symbol": symbol, "timestamp": datetime.now().isoformat()}

    @mcp.resource("crypto://{symbol}")
    async def get_crypto_price(
        symbol: str, provider: str = "tiingo", quote: str = "usd"
    ) -> dict[str, Any]:
        """
        Get current and recent cryptocurrency price data.

        Supports both Tiingo and Binance providers.
        """
        cache_key = f"crypto:{symbol}:{provider}:{quote}"

        # Check cache first
        if _is_cache_valid(cache_key):
            return _resource_cache[cache_key]["data"]

        try:
            # Fetch last 5 days of data
            df = await _market_data.get_crypto_historical_data(
                symbol, lookback_days=5, provider=provider, quote_currency=quote
            )

            latest = df.iloc[-1]
            prev_close = df.iloc[-2]["close"] if len(df) > 1 else latest["close"]

            data = {
                "symbol": symbol.upper(),
                "quote_currency": quote.upper(),
                "price": float(latest["close"]),
                "open": float(latest["open"]),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "volume": float(latest["volume"]),
                "change": float(latest["close"] - prev_close),
                "change_percent": float((latest["close"] - prev_close) / prev_close * 100),
                "timestamp": datetime.now().isoformat(),
                "provider": provider,
            }

            # Cache the result
            _resource_cache[cache_key] = {"data": data, "timestamp": datetime.now()}

            return data

        except Exception as e:
            return {
                "error": str(e),
                "symbol": symbol,
                "provider": provider,
                "timestamp": datetime.now().isoformat(),
            }

    @mcp.resource("crypto://{symbol}/history")
    async def get_crypto_history(
        symbol: str, days: int | None = 30, provider: str = "tiingo", quote: str = "usd"
    ) -> dict[str, Any]:
        """
        Get historical cryptocurrency price data.

        Returns OHLCV data for the specified number of days.
        """
        cache_key = f"crypto:{symbol}:history:{days}:{provider}:{quote}"

        # Check cache first
        if _is_cache_valid(cache_key):
            return _resource_cache[cache_key]["data"]

        try:
            df = await _market_data.get_crypto_historical_data(
                symbol, lookback_days=days, provider=provider, quote_currency=quote
            )

            # Convert DataFrame to list of dictionaries
            history = []
            for date, row in df.iterrows():
                history.append(
                    {
                        "date": date.isoformat(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    }
                )

            data = {
                "symbol": symbol.upper(),
                "quote_currency": quote.upper(),
                "days": days,
                "data": history,
                "timestamp": datetime.now().isoformat(),
                "provider": provider,
            }

            # Cache the result
            _resource_cache[cache_key] = {"data": data, "timestamp": datetime.now()}

            return data

        except Exception as e:
            return {
                "error": str(e),
                "symbol": symbol,
                "provider": provider,
                "timestamp": datetime.now().isoformat(),
            }

    @mcp.resource("market://cache/clear")
    async def clear_cache() -> dict[str, Any]:
        """
        Clear the resource cache.

        Useful for forcing fresh data retrieval.
        """
        _resource_cache.clear()
        return {
            "status": "success",
            "message": "Cache cleared",
            "timestamp": datetime.now().isoformat(),
        }

    @mcp.resource("market://cache/status")
    async def cache_status() -> dict[str, Any]:
        """
        Get current cache status and statistics.
        """
        entries = []
        for key, value in _resource_cache.items():
            age = (datetime.now() - value["timestamp"]).total_seconds()
            entries.append({"key": key, "age_seconds": age, "expired": age >= _cache_ttl})

        return {
            "total_entries": len(_resource_cache),
            "ttl_seconds": _cache_ttl,
            "entries": entries,
            "timestamp": datetime.now().isoformat(),
        }

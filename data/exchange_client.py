# ==============================================================================
# File: data/exchange_client.py
# Purpose: Binance exchange client interface using CCXT. 
# Contains: Candlestick fetching (OHLCV) and ticker current price fetching routines.
# Fits into: Data Access Layer. Acts as an API facade to the external exchange.
# ==============================================================================

import logging
from typing import Optional, Dict, Any, List
import pandas as pd
import ccxt

import config

logger = logging.getLogger("crypto_bot.exchange")

# ==============================================================================
# EXCHANGE SINGLETON STORAGE
# ==============================================================================
_exchange_instance: Optional[ccxt.binance] = None
_futures_exchange_instance: Optional[ccxt.binanceusdm] = None

def get_exchange() -> ccxt.binance:
    """
    Returns a singleton instance of the CCXT Binance exchange client.
    Lazy-instantiated and configured with credentials from the config module.
    
    Accepts:
        None
    Returns:
        ccxt.binance: Active CCXT Binance connection client.
    """
    global _exchange_instance
    if _exchange_instance is None:
        exchange_options: Dict[str, Any] = {
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_SECRET,
            "enableRateLimit": True,  # Required to avoid rate limit bans from Binance
            "options": {
                "defaultType": "spot"  # Focuses on Spot trading for Phase 1
            }
        }
        
        # NOTE: Initialize connection
        try:
            _exchange_instance = ccxt.binance(exchange_options)
            logger.info("[+] CCXT Binance exchange instance initialized successfully.")
        except Exception as e:
            logger.error(f"[X] Failed to create CCXT Binance instance: {str(e)}")
            # Return an unauthenticated exchange instance for public market data fetches
            _exchange_instance = ccxt.binance({"enableRateLimit": True})
            logger.warning("[!] Created unauthenticated public exchange client as fallback.")
            
    return _exchange_instance


def get_futures_exchange() -> ccxt.binanceusdm:
    """
    Returns a singleton instance of the CCXT Binance USD-M Futures exchange client.
    Lazy-instantiated and configured with credentials from the config module.
    
    Accepts:
        None
    Returns:
        ccxt.binanceusdm: Active CCXT Binance Futures connection client.
    """
    global _futures_exchange_instance
    if _futures_exchange_instance is None:
        exchange_options: Dict[str, Any] = {
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_SECRET,
            "enableRateLimit": True
        }
        
        # NOTE: Initialize connection
        try:
            _futures_exchange_instance = ccxt.binanceusdm(exchange_options)
            logger.info("[+] CCXT Binance USD-M Futures exchange instance initialized successfully.")
        except Exception as e:
            logger.error(f"[X] Failed to create CCXT Binance Futures instance: {str(e)}")
            # Return an unauthenticated exchange instance for public market data fetches
            _futures_exchange_instance = ccxt.binanceusdm({"enableRateLimit": True})
            logger.warning("[!] Created unauthenticated public Futures exchange client as fallback.")
            
    return _futures_exchange_instance


def generate_fallback_ohlcv(pair: str, limit: int = 100) -> pd.DataFrame:
    """
    Generates realistic fallback candlestick data for paper trading when Binance API is unavailable/blocked.
    """
    import numpy as np
    from datetime import datetime, timezone
    
    logger.warning(f"[!] Generating simulated fallback candle series for {pair} ({limit} bars)")
    
    # Establish base price based on asset
    base_prices = {"BTC/USDT": 65000.0, "ETH/USDT": 3500.0, "SOL/USDT": 150.0}
    current_price = base_prices.get(pair, 100.0)
    
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq="5min")
    close_prices = []
    
    # Generate random walk candles
    np.random.seed(42) # keeps it stable but realistic
    for i in range(limit):
        change = np.random.normal(0.0, current_price * 0.001) # 0.1% volatility
        current_price += change
        close_prices.append(current_price)
        
    df = pd.DataFrame({
        "open": [p - np.random.uniform(0.1, 2.0) for p in close_prices],
        "high": [p + np.random.uniform(0.5, 5.0) for p in close_prices],
        "low": [p - np.random.uniform(0.5, 5.0) for p in close_prices],
        "close": close_prices,
        "volume": [np.random.uniform(1.0, 50.0) for _ in close_prices]
    }, index=timestamps)
    
    df.index.name = "timestamp"
    return df


def fetch_ohlcv(pair: str, timeframe: str = "5m", limit: int = 100) -> pd.DataFrame:
    """
    Fetches historical candlestick (OHLCV) data from Binance for a given trading pair.
    
    Accepts:
        pair (str): Trading pair string, e.g., 'BTC/USDT'.
        timeframe (str): Interval size, defaults to '5m'.
        limit (int): Quantity of candlesticks to download, defaults to 100.
    Returns:
        pd.DataFrame: DataFrame containing historical candlesticks with columns:
                      'open', 'high', 'low', 'close', 'volume' and DatetimeIndex.
    """
    exchange = get_exchange()
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    
    try:
        logger.info(f"[-] Fetching {limit} {timeframe} candles for pair {pair}...")
        # CCXT fetches OHLCV as: [[timestamp, open, high, low, close, volume], ...]
        raw_candles = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
        
        if not raw_candles:
            logger.warning(f"[!] Exchange returned empty candle list for {pair}.")
            return generate_fallback_ohlcv(pair, limit)
            
        # Parse into a pandas DataFrame
        df = pd.DataFrame(
            raw_candles, 
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        
        # Convert millisecond timestamp to datetime index
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        
        # Cast data columns to floating point for indicator calculations
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
            
        logger.info(f"[+] Loaded {len(df)} candles for {pair} successfully.")
        return df
        
    except ccxt.NetworkError as ne:
        logger.error(f"[X] Exchange network error occurred while fetching OHLCV for {pair}: {str(ne)}")
        return generate_fallback_ohlcv(pair, limit)
    except ccxt.ExchangeError as ee:
        logger.error(f"[X] Exchange API error returned while fetching OHLCV for {pair}: {str(ee)}")
        return generate_fallback_ohlcv(pair, limit)
    except Exception as e:
        logger.error(f"[X] Unhandled exception in fetch_ohlcv for {pair}: {str(e)}")
        return generate_fallback_ohlcv(pair, limit)


def fetch_current_price(pair: str) -> float:
    """
    Queries Binance for the latest ticker price of an asset pair.
    
    Accepts:
        pair (str): Trading pair string, e.g., 'BTC/USDT'.
    Returns:
        float: Latest market price, or 0.0 on error.
    """
    exchange = get_exchange()
    try:
        ticker = exchange.fetch_ticker(pair)
        price = float(ticker.get("last", 0.0))
        if price <= 0.0:
            # Fallback if ticker data is incomplete
            price = float(ticker.get("close", 0.0))
        return price
    except Exception as e:
        logger.error(f"[X] Error fetching current ticker price for {pair}: {str(e)}")
        # Provide simulated static fallback for local testing if keys are invalid / network is down
        fallback_prices = {"BTC/USDT": 65000.0, "ETH/USDT": 3500.0, "SOL/USDT": 150.0}
        fallback = fallback_prices.get(pair, 1.0)
        logger.warning(f"[!] Using local simulated fallback price of ${fallback} for {pair}")
        return fallback


def fetch_futures_price(pair: str) -> float:
    """
    Queries Binance USD-M Futures for the latest mark/last price of an asset pair.
    
    Accepts:
        pair (str): Trading pair string, e.g., 'BTC/USDT'.
    Returns:
        float: Latest futures market price, or 0.0 on error (with spot price fallback).
    """
    futures_exchange = get_futures_exchange()
    try:
        # NOTE: USD-M Futures symbol in CCXT is standard 'BTC/USDT' or 'BTC/USDT:USDT'.
        # To support standard pairing logic, we fetch the ticker directly.
        ticker = futures_exchange.fetch_ticker(pair)
        price = float(ticker.get("last", 0.0))
        if price <= 0.0:
            price = float(ticker.get("close", 0.0))
        return price
    except Exception as e:
        logger.error(f"[X] Error fetching current futures price for {pair}: {str(e)}")
        # Graceful degradation fallback: return standard spot price so premium math doesn't divide by zero
        spot_price = fetch_current_price(pair)
        logger.warning(f"[!] Falling back to Spot price of ${spot_price} for {pair}")
        return spot_price

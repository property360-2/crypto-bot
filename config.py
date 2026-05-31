# ==============================================================================
# File: config.py
# Purpose: Central configuration loader and validator for the Crypto Trading Bot.
# Contains: Environment variable bindings, trading constants, and default settings.
# Fits into: Main core configurations, imported across the bot for consistent settings.
# ==============================================================================

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load local environment variables from a .env file if it exists (for local development)
load_dotenv()

# ==============================================================================
# TRADING SYSTEM CONSTANTS
# ==============================================================================
# NOTE: These values define the default risk parameters of the system.
# Some of these parameters (like trading pairs, mode) can be overridden by 
# dynamic Firebase Firestore configurations.

# Risk management settings
STOP_LOSS_PCT: float = 0.03       # Stop Loss is set at 3% below entry price
TAKE_PROFIT_PCT: float = 0.06      # Take Profit is set at 6% above entry price (2:1 reward-to-risk)
RISK_PER_TRADE: float = 0.10       # Use 10% of total available capital per trade position
MAX_OPEN_TRADES: int = 2          # Maximum of 2 simultaneous open positions
COOLDOWN_CYCLES: int = 1           # Cooldown periods in loops/cycles after a Stop Loss triggers (wait 5 mins)

# Default market parameters
DEFAULT_PAIRS: List[str] = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
CANDLE_TIMEFRAME: str = "5m"       # Candle size (5 minutes)
CANDLE_LOOKBACK: int = 100         # Amount of historical candles to fetch for calculation

# ==============================================================================
# ENVIRONMENT VARIABLES LOADER AND VALIDATOR
# ==============================================================================

# System operational parameters
PORT: int = int(os.getenv("PORT", "8000"))
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()

# Exchange API Credentials
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET: str = os.getenv("BINANCE_SECRET", "")

# Firebase Admin SDK Configuration JSON (Base64 or raw JSON string allowed)
# This raw service account details string is mandatory for Firebase initialization.
FIREBASE_CREDENTIALS: str = os.getenv("FIREBASE_CREDENTIALS", "")

# Notification Alerts (Optional, fails gracefully)
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# CryptoPanic API Token (Optional, falls back gracefully)
CRYPTOPANIC_TOKEN: str = os.getenv("CRYPTOPANIC_TOKEN", "")

# Phase 2 LLM Sentiment API (Optional, falls back gracefully)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

def validate_config() -> None:
    """
    Validates that all essential config parameters are present.
    Raises ValueError if critical environment variables are missing.
    
    Accepts:
        None
    Returns:
        None
    Raises:
        ValueError: If a required environment variable is not populated.
    """
    # NOTE: Firebase Firestore credentials and Binance keys are critical.
    # Without them, the bot cannot load balances, save logs, or fetch live price data.
    missing_vars = []
    
    if not FIREBASE_CREDENTIALS:
        missing_vars.append("FIREBASE_CREDENTIALS")
    if not BINANCE_API_KEY:
        missing_vars.append("BINANCE_API_KEY")
    if not BINANCE_SECRET:
        missing_vars.append("BINANCE_SECRET")
        
    if missing_vars:
        raise ValueError(
            f"[!] Configuration validation failed. Missing required environment variable(s): {', '.join(missing_vars)}. "
            f"Please check your .env file or Render service environment configuration."
        )

# Validate config at start to fail fast if required environment values are missing
if ENVIRONMENT != "development":
    # Let local development be lenient during structural scaffolding,
    # but strictly validate in production.
    validate_config()

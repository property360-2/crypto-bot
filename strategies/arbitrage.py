# ==============================================================================
# File: strategies/arbitrage.py
# Purpose: Spot vs Futures Premium Arbitrage Spread Strategy.
# Fits into: Strategy component namespace.
# ==============================================================================

import logging
from typing import Dict, Any

from data import exchange_client

logger = logging.getLogger("crypto_bot.strategies.arbitrage")

def analyze(pair: str) -> Dict[str, Any]:
    """
    Checks the price premium spread percentage between Binance Spot and Binance USD-M Futures.
    Maps premium percentage to Contango (+0.5) or Backwardation (-0.5) signal weights.
    
    Accepts:
        pair (str): Trading pair string, e.g., 'BTC/USDT'.
    Returns:
        Dict[str, Any]: Arbitrage strategy report containing:
            - 'signal' (float): Premium mapped signal score (-1.0 to +1.0).
            - 'action' (str): Recommended action ('BUY', 'SELL', 'HOLD').
            - 'indicators' (dict): Spot and Futures price metrics.
            - 'reasons' (list[str]): Explanation audit log.
    """
    logger.info(f"[-] Running Spot vs Futures premium analysis for {pair}...")
    reasons = []
    
    fallback_report = {
        "signal": 0.0,
        "action": "HOLD",
        "indicators": {
            "spot_price": 0.0,
            "futures_price": 0.0,
            "premium_pct": 0.0
        },
        "reasons": ["Premium calculation failed. Defaulting to neutral (0.0)."]
    }

    try:
        # 1. Fetch current Spot and Futures prices
        spot_price = exchange_client.fetch_current_price(pair)
        futures_price = exchange_client.fetch_futures_price(pair)
        
        if spot_price <= 0.0 or futures_price <= 0.0:
            logger.warning(f"[!] Invalid price data for {pair} (Spot: {spot_price}, Futures: {futures_price}). Skipping.")
            return fallback_report

        # 2. Compute the Premium Spread Percentage
        # Formula: ((Futures - Spot) / Spot) * 100
        premium_pct = ((futures_price - spot_price) / spot_price) * 100.0
        
        reasons.append(f"Spot price: ${spot_price:,.4f} | Futures price: ${futures_price:,.4f}")
        reasons.append(f"Calculated premium spread: {premium_pct:+.4f}%")

        # 3. Map Premium to Quantitative Sentiment Score
        # Rules:
        # - Contango: Premium >= 0.3% -> Bullish signal (+0.5)
        # - Backwardation: Premium <= -0.1% -> Bearish signal (-0.5)
        # - Neutral: Premium between -0.1% and 0.3% -> Neutral signal (0.0)
        
        signal_score = 0.0
        if premium_pct >= 0.3:
            signal_score = 0.5
            reasons.append(f"Market in Contango (Premium {premium_pct:+.2f}% >= +0.3%): Bullish market signal (+0.5)")
        elif premium_pct <= -0.1:
            signal_score = -0.5
            reasons.append(f"Market in Backwardation (Premium {premium_pct:+.2f}% <= -0.1%): Bearish market signal (-0.5)")
        else:
            signal_score = 0.0
            reasons.append(f"Market premium neutral (Premium {premium_pct:+.2f}% in range -0.1% to +0.3%): Neutral signal (0.0)")

        # Determine strategy recommended action
        action = "HOLD"
        if signal_score >= 0.3:
            action = "BUY"
        elif signal_score <= -0.3:
            action = "SELL"

        report = {
            "signal": signal_score,
            "action": action,
            "indicators": {
                "spot_price": spot_price,
                "futures_price": futures_price,
                "premium_pct": round(premium_pct, 4)
            },
            "reasons": reasons
        }
        
        logger.info(f"[+] Arbitrage analysis complete for {pair}. Signal: {signal_score:+.1f}, Action: {action}")
        return report

    except Exception as e:
        logger.error(f"[X] Exception during arbitrage premium analysis: {str(e)}")
        return fallback_report

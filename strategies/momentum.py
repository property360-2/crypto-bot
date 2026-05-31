# ==============================================================================
# File: strategies/momentum.py
# Purpose: Momentum trading strategy using RSI, MACD, and Double EMA crossover.
# Contains: Indicator computation and quantitative signal scoring algorithms.
# Fits into: Strategy component namespace.
# ==============================================================================

import logging
from typing import Dict, Any, List
import pandas as pd
import pandas_ta_classic as ta  # Extends pandas DataFrame namespace with technical indicators

logger = logging.getLogger("crypto_bot.strategies.momentum")

def analyze(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes technical indicators (RSI, MACD, EMA 20/50) and generates 
    quantitative signals with a breakdown of reasoning.
    
    Accepts:
        df (pd.DataFrame): Historical market candles containing 'close' prices.
    Returns:
        Dict[str, Any]: Strategy report containing:
            - 'signal' (float): Normalized combined momentum score (-1.0 to +1.0).
            - 'action' (str): Recommended action ('BUY', 'SELL', 'HOLD').
            - 'indicators' (dict): Key metric values at the latest index.
            - 'reasons' (list[str]): Explanation log behind the signals.
    """
    # Safe structure initialization in case calculations fail
    fallback_report = {
        "signal": 0.0,
        "action": "HOLD",
        "indicators": {},
        "reasons": ["Insufficient data or calculations failed."]
    }

    if df.empty or len(df) < 50:
        logger.warning(f"[!] Insufficient candle data to compute indicators. Required: 50, Found: {len(df)}")
        return fallback_report

    try:
        # ==============================================================================
        # INDICATOR CALCULATIONS
        # ==============================================================================
        # NOTE: pandas-ta automatically appends the generated Series to the active namespace
        
        # Calculate Relative Strength Index (RSI 14)
        rsi_series = df.ta.rsi(length=14)
        if rsi_series is None or rsi_series.empty:
            logger.warning("[!] Failed to compute RSI series.")
            return fallback_report
            
        # Calculate Exponential Moving Averages (EMA 20 and EMA 50)
        ema20_series = df.ta.ema(length=20)
        ema50_series = df.ta.ema(length=50)
        if ema20_series is None or ema50_series is None:
            logger.warning("[!] Failed to compute EMA 20 or EMA 50.")
            return fallback_report
            
        # Calculate Moving Average Convergence Divergence (MACD 12, 26, 9)
        macd_df = df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is None or macd_df.empty:
            logger.warning("[!] Failed to compute MACD.")
            return fallback_report

        # Ensure correct column naming mapping for standard MACD output
        macd_col = "MACD_12_26_9"
        macds_col = "MACDs_12_26_9"
        macdh_col = "MACDh_12_26_9"

        if macd_col not in macd_df or macds_col not in macd_df or macdh_col not in macd_df:
            # Fallback scan of columns if pandas-ta naming differs
            cols = list(macd_df.columns)
            macd_col = cols[0]
            macds_col = cols[1]
            macdh_col = cols[2]

        # Assemble temporary indicators in main dataframe for clean alignment
        df_indicators = df.copy()
        df_indicators["RSI_14"] = rsi_series
        df_indicators["EMA_20"] = ema20_series
        df_indicators["EMA_50"] = ema50_series
        df_indicators["MACD"] = macd_df[macd_col]
        df_indicators["MACD_signal"] = macd_df[macds_col]
        df_indicators["MACD_hist"] = macd_df[macdh_col]

        # Clean NaN rows resulting from initial moving windows
        df_indicators.dropna(subset=["RSI_14", "EMA_20", "EMA_50", "MACD"], inplace=True)

        if len(df_indicators) < 2:
            logger.warning("[!] Insufficient valid data rows left after removing NaNs.")
            return fallback_report

        # ==============================================================================
        # LATEST DATA POINTS EXTRACTION
        # ==============================================================================
        current_row = df_indicators.iloc[-1]
        previous_row = df_indicators.iloc[-2]

        current_rsi = float(current_row["RSI_14"])
        current_ema20 = float(current_row["EMA_20"])
        current_ema50 = float(current_row["EMA_50"])
        current_macd = float(current_row["MACD"])
        current_macd_sig = float(current_row["MACD_signal"])
        current_macd_hist = float(current_row["MACD_hist"])

        prev_macd_hist = float(previous_row["MACD_hist"])

        # ==============================================================================
        # TRIGGER LOGIC DEFINITIONS
        # ==============================================================================
        # Bullish cross: MACD histogram turns positive from a negative value
        macd_bullish_cross = (prev_macd_hist < 0) and (current_macd_hist > 0)
        # Bearish cross: MACD histogram turns negative from a positive value
        macd_bearish_cross = (prev_macd_hist > 0) and (current_macd_hist < 0)

        ema_bullish = current_ema20 > current_ema50
        ema_bearish = current_ema20 < current_ema50

        # ==============================================================================
        # QUANTITATIVE SCORE MATRIX (-1.0 to +1.0)
        # ==============================================================================
        score = 0.0
        reasons = []

        # 1. RSI Scoring
        if current_rsi < 30:
            score += 0.4
            reasons.append(f"RSI oversold ({current_rsi:.2f}): Bullish indicator (+0.4)")
        elif current_rsi >= 30 and current_rsi < 50:
            score += 0.2
            reasons.append(f"RSI moderately low ({current_rsi:.2f}): Light bullish momentum (+0.2)")
        elif current_rsi > 70 and current_rsi <= 80:
            score -= 0.3
            reasons.append(f"RSI overbought ({current_rsi:.2f}): Bearish exhaustion (-0.3)")
        elif current_rsi > 80:
            score -= 0.5
            reasons.append(f"RSI critically overbought ({current_rsi:.2f}): Heavy sell risk (-0.5)")
        else:
            reasons.append(f"RSI neutral ({current_rsi:.2f}) (0.0)")

        # 2. MACD Crossover Scoring
        if macd_bullish_cross:
            score += 0.3
            reasons.append("MACD bullish crossover detected (+0.3)")
        elif macd_bearish_cross:
            score -= 0.3
            reasons.append("MACD bearish crossover detected (-0.3)")
        else:
            reasons.append(f"MACD histogram stable at {current_macd_hist:.4f} (0.0)")

        # 3. EMA Trend Alignment Scoring
        if ema_bullish:
            score += 0.3
            reasons.append(f"EMA 20 > EMA 50: Uptrend alignment (+0.3)")
        elif ema_bearish:
            score -= 0.3
            reasons.append(f"EMA 20 < EMA 50: Downtrend alignment (-0.3)")

        # Clamp final score between -1.0 and +1.0
        final_score = max(-1.0, min(1.0, score))

        # ==============================================================================
        # DECISION ENGINE
        # ==============================================================================
        action = "HOLD"
        
        # BUY Trigger: RSI is not overbought AND MACD crossed bullish AND we are in an uptrend
        buy_condition = (current_rsi < 70) and macd_bullish_cross and ema_bullish
        
        # SELL Trigger: RSI is overbought OR MACD crossed bearish OR we transitioned into a downtrend
        sell_condition = (current_rsi > 75) or macd_bearish_cross or ema_bearish

        if buy_condition:
            action = "BUY"
            reasons.append(">>> Confluence met: Trigger BUY Action.")
        elif sell_condition:
            action = "SELL"
            reasons.append(">>> Risk threshold or trend change met: Trigger SELL Action.")
        else:
            reasons.append("Confluence not met. Action set to HOLD.")

        report = {
            "signal": round(final_score, 2),
            "action": action,
            "indicators": {
                "rsi": round(current_rsi, 2),
                "macd": round(current_macd, 6),
                "macd_signal": round(current_macd_sig, 6),
                "macd_histogram": round(current_macd_hist, 6),
                "ema_20": round(current_ema20, 2),
                "ema_50": round(current_ema50, 2),
            },
            "reasons": reasons
        }
        
        logger.info(f"[+] Momentum analysis complete for asset. Action: {action}, Score: {final_score}")
        return report

    except Exception as e:
        logger.error(f"[X] Exception during momentum analysis computation: {str(e)}")
        return fallback_report

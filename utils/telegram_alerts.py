# ==============================================================================
# File: utils/telegram_alerts.py
# Purpose: Telegram Notification Alerts Interface. Delivers real-time trade signals,
#          status changes, and exits to the user's Telegram channel.
# Fits into: Support utilities package.
# ==============================================================================

import logging
from typing import Dict, Any, Optional
import httpx

import config

logger = logging.getLogger("crypto_bot.utils.telegram")

# ==============================================================================
# HTTP NOTIFICATION BROADCASTER
# ==============================================================================

async def send_alert(message: str) -> bool:
    """
    Delivers a message text payload directly to the Telegram chat target.
    Degrades gracefully (fails silently) if Telegram environment variables 
    are missing, logging to console instead.
    
    Accepts:
        message (str): Plain or Markdown-formatted alert message text.
    Returns:
        bool: True if message sent successfully, False otherwise.
    """
    token = config.TELEGRAM_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.info(f"[-] [Telegram Alert (Muted)]: {message}")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        # NOTE: Direct non-blocking asynchronous call to Telegram Bot Endpoint API
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=payload)
            if response.status_code == 200:
                logger.info("[+] Telegram notification delivered successfully.")
                return True
            else:
                logger.error(
                    f"[X] Telegram API returned non-success code {response.status_code}. "
                    f"Response: {response.text}"
                )
                return False
    except httpx.HTTPError as he:
        logger.error(f"[X] HTTP network error occurred during Telegram notification dispatch: {str(he)}")
        return False
    except Exception as e:
        logger.error(f"[X] Unexpected error while sending Telegram notification: {str(e)}")
        return False

# ==============================================================================
# MESSAGE FORMATTERS
# ==============================================================================

def format_trade_alert(trade: Dict[str, Any]) -> str:
    """
    Formats opening and closing trade dict variables into beautiful markdown 
    templates loaded with visual indicator emojis.
    
    Accepts:
        trade (dict): Logged trade details.
    Returns:
        str: Fully formatted markdown text ready for Telegram delivery.
    """
    try:
        pair = trade.get("pair", "UNKNOWN")
        action = trade.get("action", "BUY")
        status = trade.get("status", "open")
        mode = trade.get("mode", "paper").upper()
        
        # Opening Trade Layout
        if status == "open":
            entry = float(trade.get("entry_price", 0.0))
            qty = float(trade.get("quantity", 0.0))
            cost = float(trade.get("cost", 0.0))
            sl = float(trade.get("stop_loss", 0.0))
            tp = float(trade.get("take_profit", 0.0))
            score = float(trade.get("final_signal_score", 0.0))

            return (
                f"🟢 *[{mode}] POSITION OPENED*\n\n"
                f"▪️ *Asset Pair:* `{pair}`\n"
                f"▪️ *Action:* `BUY (LONG)`\n"
                f"▪️ *Entry Price:* `${entry:.4f}`\n"
                f"▪️ *Position Cost:* `${cost:.2f} USDT`\n"
                f"▪️ *Quantity:* `{qty:.6f}`\n"
                f"▪️ *Stop Loss:* `${sl:.4f}`\n"
                f"▪️ *Take Profit:* `${tp:.4f}`\n"
                f"▪️ *Confluence Score:* `{score:+.2f}`\n\n"
                f"🚀 _Monitoring market movements closely..._"
            )
            
        # Closing Trade Layout
        else:
            entry = float(trade.get("entry_price", 0.0))
            exit_price = float(trade.get("exit_price", 0.0))
            qty = float(trade.get("quantity", 0.0))
            cost = float(trade.get("cost", 0.0))
            pnl = float(trade.get("pnl", 0.0))
            reason = trade.get("close_reason", "SL/TP").upper()
            
            pnl_pct = (pnl / cost) * 100.0 if cost > 0.0 else 0.0
            emoji = "🟢" if pnl > 0.0 else "🔴"
            outcome = "PROFIT" if pnl > 0.0 else "LOSS"

            return (
                f"{emoji} *[{mode}] POSITION CLOSED ({reason})*\n\n"
                f"▪️ *Asset Pair:* `{pair}`\n"
                f"▪️ *Entry Price:* `${entry:.4f}`\n"
                f"▪️ *Exit Price:* `${exit_price:.4f}`\n"
                f"▪️ *Quantity:* `{qty:.6f}`\n"
                f"▪️ *Trade Outcome:* *{outcome}*\n"
                f"▪️ *Realized PnL:* `{pnl:+.4f} USDT` (`{pnl_pct:+.2f}%`)\n\n"
                f"💰 _Available trading balance updated..._"
            )
            
    except Exception as e:
        logger.error(f"[X] Error formatting trade alert: {str(e)}")
        return f"⚠️ [Alert Format Error] Failed to compile trade notification text: {str(e)}"


def format_signal_alert(pair: str, signal_report: Dict[str, Any]) -> str:
    """
    Formats a calculated strategy meta-signal report for developer auditing.
    
    Accepts:
        pair (str): Trading pair.
        signal_report (dict): Consolidated decision output.
    Returns:
        str: Fully formatted markdown text representation.
    """
    try:
        action = signal_report.get("action", "HOLD")
        score = float(signal_report.get("final_signal", 0.0))
        reasons = signal_report.get("reasons", [])
        
        reasons_bulleted = "\n".join([f"• {r}" for r in reasons])
        
        emoji = "⚪"
        if action == "STRONG_BUY":
            emoji = "🟢"
        elif action == "STRONG_SELL":
            emoji = "🔴"
            
        return (
            f"🔍 *[MARKET SCANNER]* `{pair}`\n"
            f"▪️ *Action Score:* {emoji} `{action}` (`{score:+.2f}`)\n\n"
            f"*Analysis Log:*\n"
            f"{reasons_bulleted}"
        )
    except Exception as e:
        logger.error(f"[X] Error formatting signal alert: {str(e)}")
        return f"⚠️ [Alert Format Error] Failed to compile market scan log: {str(e)}"

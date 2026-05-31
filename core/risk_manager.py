# ==============================================================================
# File: core/risk_manager.py
# Purpose: Risk Management Engine. Validates trade requirements, sizing, 
#          exit parameters (Stop Loss/Take Profit), and system cooldown limits.
# Fits into: Risk Core component.
# ==============================================================================

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

import config

logger = logging.getLogger("crypto_bot.core.risk_manager")

def is_in_cooldown(last_sl_time: Optional[datetime]) -> bool:
    """
    Checks if the bot is currently in a cooldown state after a recent stop loss hit.
    
    Accepts:
        last_sl_time (Optional[datetime]): Timestamp of the last hit stop loss.
    Returns:
        bool: True if the current time is within 5 minutes of the last loss, False otherwise.
    """
    if last_sl_time is None:
        return False
        
    try:
        now = datetime.now(timezone.utc)
        # Ensure last_sl_time is timezone-aware
        if last_sl_time.tzinfo is None:
            last_sl_time = last_sl_time.replace(tzinfo=timezone.utc)
            
        difference = (now - last_sl_time).total_seconds()
        
        # Cooldown cycle is 5 minutes (300 seconds)
        cooldown_seconds = config.COOLDOWN_CYCLES * 300
        in_cooldown = difference < cooldown_seconds
        
        if in_cooldown:
            remaining = int(cooldown_seconds - difference)
            logger.warning(f"[!] Cooldown active. Last stop loss hit {int(difference)}s ago. Remaining: {remaining}s")
            
        return in_cooldown
    except Exception as e:
        logger.error(f"[X] Exception checking cooldown state: {str(e)}")
        return False


def can_trade(
    balance: float, 
    open_trades: List[Dict[str, Any]], 
    last_sl_time: Optional[datetime] = None,
    fear_greed_score: int = 50
) -> Tuple[bool, str]:
    """
    Validates trade risk gates to ensure the system is allowed to open a new position.
    
    Accepts:
        balance (float): Current available USDT capital.
        open_trades (list): List of currently active/open positions.
        last_sl_time (datetime, optional): Time of last hit stop loss.
        fear_greed_score (int): Current Alternative.me Fear & Greed index score (default 50).
    Returns:
        Tuple[bool, str]: (is_allowed, reason_message)
    """
    try:
        # Rule 1: Never trade if balance is too low
        if balance < 1.0:
            return False, f"USDT Balance (${balance:.2f}) too low to size new position (minimum $1.00)."
            
        # Rule 2: Max 2 simultaneous open positions
        if len(open_trades) >= config.MAX_OPEN_TRADES:
            return False, f"Maximum open trades limit reached ({len(open_trades)}/{config.MAX_OPEN_TRADES})."
            
        # Rule 3: Enforce cooldown period after any stop loss hit
        if is_in_cooldown(last_sl_time):
            return False, "Bot is in cooldown cycle after hitting a Stop Loss recently."
            
        # Rule 4: Never trade during extreme fear (Fear & Greed < 20)
        if fear_greed_score < 20:
            return False, f"Trading blocked due to extreme market fear (Fear & Greed Index: {fear_greed_score} < 20)."
            
        return True, "Passed all risk gates. Trade allowed."
        
    except Exception as e:
        logger.error(f"[X] Error running can_trade risk validation: {str(e)}")
        return False, f"Risk validation error: {str(e)}"


def calculate_position(balance: float, entry_price: float) -> Dict[str, Any]:
    """
    Calculates position sizing, trade quantity, stop-loss and take-profit price levels.
    
    Accepts:
        balance (float): Total available USDT capital.
        entry_price (float): Asset entry market price.
    Returns:
        Dict[str, Any]: Sizing values containing 'quantity', 'cost', 'stop_loss', 
                        and 'take_profit'.
    """
    try:
        # Sizing Cost = 10% of total balance
        position_cost = balance * config.RISK_PER_TRADE
        
        # Quantity to purchase
        quantity = position_cost / entry_price
        
        # Stop loss is set at 3% below entry price
        stop_loss_price = entry_price * (1.0 - config.STOP_LOSS_PCT)
        
        # Take profit is set at 6% above entry price
        take_profit_price = entry_price * (1.0 + config.TAKE_PROFIT_PCT)
        
        position_details = {
            "quantity": quantity,
            "cost": position_cost,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price
        }
        
        logger.info(
            f"[+] Computed Position: Size=${position_cost:.2f} USDT, Qty={quantity:.6f}, "
            f"SL=${stop_loss_price:.4f}, TP=${take_profit_price:.4f}"
        )
        return position_details
        
    except Exception as e:
        logger.error(f"[X] Error calculating position parameters: {str(e)}")
        # Return fallback mock/empty position info to avoid system crashes
        return {
            "quantity": 0.0,
            "cost": 0.0,
            "stop_loss": entry_price,
            "take_profit": entry_price
        }


def check_stop_loss_take_profit(trade: Dict[str, Any], current_price: float) -> Optional[str]:
    """
    Evaluates whether an active trade has crossed its stop-loss or take-profit price thresholds.
    
    Accepts:
        trade (dict): Logged trade details containing 'stop_loss' and 'take_profit' limits.
        current_price (float): Current market ticker price.
    Returns:
        Optional[str]: 'stop_loss' if stop limit crossed, 
                      'take_profit' if profit target crossed, 
                      None if still active.
    """
    try:
        action = trade.get("action", "BUY")
        stop_loss = float(trade.get("stop_loss", 0.0))
        take_profit = float(trade.get("take_profit", 0.0))
        
        # NOTE: Handle trade direction (BUY/Long position assumed for default)
        if action == "BUY":
            if current_price <= stop_loss:
                return "stop_loss"
            elif current_price >= take_profit:
                return "take_profit"
        
        return None
        
    except Exception as e:
        logger.error(f"[X] Error checking stop loss or take profit crossings: {str(e)}")
        return None

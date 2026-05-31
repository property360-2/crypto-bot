# ==============================================================================
# File: core/executor.py
# Purpose: Paper Trading Execution Engine. Simulates buy and sell orders,
#          monitors current open trade states, and handles balance deductions.
# Fits into: Execution Core component.
# ==============================================================================

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from data import firebase_client
from core import risk_manager
import config

logger = logging.getLogger("crypto_bot.core.executor")

# ==============================================================================
# ENTRY POINT SIGNAL EXECUTION
# ==============================================================================

def execute_signal(
    pair: str, 
    signal_report: Dict[str, Any], 
    current_price: float,
    fear_greed_score: int = 50
) -> Optional[Dict[str, Any]]:
    """
    Evaluates a meta-signal decision and triggers paper order execution if
    risk conditions permit.
    
    Accepts:
        pair (str): Trading pair, e.g., 'BTC/USDT'.
        signal_report (dict): Consolidated decision output from signal_combiner.
        current_price (float): Latest market price ticker.
        fear_greed_score (int): Current Alternative.me Fear & Greed index score (default 50).
    Returns:
        Optional[Dict[str, Any]]: Logged trade dictionary if opened, None otherwise.
    """
    action = signal_report.get("action", "HOLD")
    if action != "STRONG_BUY":
        logger.info(f"[-] Signal for {pair} is {action}. Execution skipped.")
        return None

    try:
        logger.info(f"[*] Processing STRONG_BUY signal execution for {pair}...")
        
        # 1. Fetch system state details from database
        settings = firebase_client.get_settings()
        mode = settings.get("mode", "paper")
        
        # NOTE: Phase 1 is paper trading only.
        if mode != "paper":
            logger.warning(f"[!] Live mode toggle detected. Phase 1 only supports paper trading. Defaulting to paper.")
            mode = "paper"

        balance = firebase_client.get_paper_balance()
        open_trades = firebase_client.get_open_trades()
        last_sl_time = firebase_client.get_last_stop_loss_time()

        # 2. Check if a position is already open for this exact pair
        # (Avoid holding duplicate positions for the same currency pair)
        for t in open_trades:
            if t.get("pair") == pair:
                logger.info(f"[-] Position already open for {pair}. Block duplicate entry.")
                return None

        # 3. Check risk manager gates (Max positions, cooldown cycle, minimum balance, F&G check)
        allowed, reason = risk_manager.can_trade(balance, open_trades, last_sl_time, fear_greed_score)
        if not allowed:
            logger.warning(f"[!] Risk engine blocked trade execution: {reason}")
            return None

        # 4. Compute position sizing parameters
        position = risk_manager.calculate_position(balance, current_price)
        if position["quantity"] <= 0.0:
            logger.error("[X] Computed trade quantity is zero. Aborting execution.")
            return None

        # 5. Open simulated position
        trade = _open_paper_trade(pair, current_price, position, signal_report, balance)
        return trade

    except Exception as e:
        logger.error(f"[X] Execution failed during execute_signal for {pair}: {str(e)}")
        return None

# ==============================================================================
# MONITORING AND RE-EVALUATION
# ==============================================================================

def check_open_trades(current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Checks all open positions against their exit stop-loss and take-profit targets
    using the latest market prices. Closes triggered trades.
    
    Accepts:
        current_prices (Dict[str, float]): Map of pairs to latest ticker price.
    Returns:
        List[Dict[str, Any]]: List of closed trade records.
    """
    closed_records: List[Dict[str, Any]] = []
    try:
        open_trades = firebase_client.get_open_trades()
        if not open_trades:
            return closed_records

        logger.info(f"[-] Checking {len(open_trades)} active positions against current prices...")
        
        for trade in open_trades:
            pair = trade.get("pair")
            trade_id = trade.get("id")
            
            if not pair or not trade_id:
                continue

            current_price = current_prices.get(pair, 0.0)
            if current_price <= 0.0:
                logger.warning(f"[!] Skipping exit check for {pair} due to invalid ticker price (${current_price}).")
                continue

            # Check if SL or TP thresholds are violated
            trigger = risk_manager.check_stop_loss_take_profit(trade, current_price)
            if trigger:
                logger.info(f"[!] Exit trigger '{trigger}' hit for {pair} at ${current_price:.4f}")
                closed_trade = _close_paper_trade(trade_id, trade, current_price, trigger)
                if closed_trade:
                    closed_records.append(closed_trade)
                    
        return closed_records
        
    except Exception as e:
        logger.error(f"[X] Exception running open trades check: {str(e)}")
        return closed_records

# ==============================================================================
# SIMULATED TRANSACTION INTERNALS
# ==============================================================================

def _open_paper_trade(
    pair: str, 
    entry_price: float, 
    position: Dict[str, Any], 
    signal_report: Dict[str, Any],
    current_balance: float
) -> Optional[Dict[str, Any]]:
    """
    Performs simulated paper trade opening. Deducts position cost from balance
    and saves the trade to Firestore.
    
    Accepts:
        pair (str): Asset pair.
        entry_price (float): Purchase price.
        position (dict): position parameters calculated by risk_manager.
        signal_report (dict): meta signals.
        current_balance (float): USDT cash before trade execution.
    Returns:
        Optional[Dict[str, Any]]: The created trade log, or None on db error.
    """
    try:
        cost = position["cost"]
        quantity = position["quantity"]
        
        # Formulate trade document structure
        trade_record = {
            "pair": pair,
            "action": "BUY",
            "entry_price": entry_price,
            "quantity": quantity,
            "cost": cost,
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "final_signal_score": signal_report.get("final_signal", 0.0),
            "strategy_signals": signal_report.get("components", {}),
            "mode": "paper",
            "status": "open",
            "pnl": None
        }

        # Deduct cost from current cash balance
        new_balance = current_balance - cost
        
        # Save order document to database
        doc_id = firebase_client.log_trade(trade_record)
        if doc_id:
            trade_record["id"] = doc_id
            # Commit the balance change
            firebase_client.update_paper_balance(new_balance)
            logger.info(f"[+] PAPER TRADE OPENED: {pair} Qty={quantity:.6f} at ${entry_price:.4f}. Cash remaining: ${new_balance:.2f} USDT")
            return trade_record
        else:
            logger.error("[X] Failed to log paper trade structure. Aborting balance deduction.")
            return None
            
    except Exception as e:
        logger.error(f"[X] Error executing internal _open_paper_trade: {str(e)}")
        return None


def _close_paper_trade(
    trade_id: str, 
    trade: Dict[str, Any], 
    exit_price: float, 
    reason: str
) -> Optional[Dict[str, Any]]:
    """
    Performs simulated paper trade closing. Re-allocates position assets back
    to available USDT cash balance and logs profit/loss.
    
    Accepts:
        trade_id (str): Database document ID of trade.
        trade (dict): Active trade document from database.
        exit_price (float): Sale execution price.
        reason (str): Context trigger description ('stop_loss' or 'take_profit').
    Returns:
        Optional[Dict[str, Any]]: Updated trade log, or None on database failure.
    """
    try:
        entry_price = float(trade.get("entry_price", 0.0))
        quantity = float(trade.get("quantity", 0.0))
        cost = float(trade.get("cost", 0.0))
        pair = trade.get("pair", "UNKNOWN")

        if entry_price <= 0.0 or quantity <= 0.0:
            logger.error(f"[X] Invalid entry metrics on trade {trade_id}. Exit aborted.")
            return None

        # Calculate proceeds from asset liquidation
        # proceeds = quantity * exit_price
        proceeds = quantity * exit_price
        pnl = proceeds - cost
        pnl_pct = (pnl / cost) * 100.0 if cost > 0.0 else 0.0
        
        # Fetch current cash balance and add simulated trade proceeds
        current_balance = firebase_client.get_paper_balance()
        new_balance = current_balance + proceeds

        # Update database record
        success = firebase_client.close_trade(trade_id, pnl, exit_price)
        if success:
            firebase_client.update_paper_balance(new_balance)
            
            # Aggregate performance analytics
            is_win = pnl > 0.0
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            firebase_client.update_daily_performance(today_str, pnl, is_win)

            trade["status"] = "closed"
            trade["exit_price"] = exit_price
            trade["pnl"] = pnl
            trade["close_reason"] = reason
            
            logger.info(
                f"[+] PAPER TRADE CLOSED: {pair} via {reason.upper()} at ${exit_price:.4f}. "
                f"PnL: ${pnl:+.4f} USDT ({pnl_pct:+.2f}%). Cash is now: ${new_balance:.2f} USDT"
            )
            return trade
        else:
            logger.error(f"[X] Failed to update close state for trade document {trade_id}")
            return None

    except Exception as e:
        logger.error(f"[X] Error executing internal _close_paper_trade: {str(e)}")
        return None

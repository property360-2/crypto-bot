# ==============================================================================
# File: data/firebase_client.py
# Purpose: Firebase Firestore CRUD layer for managing paper balances, trades, 
#          daily statistics, and dynamic configurations.
# Fits into: Data Access Layer. Handles connection initialization and error recovery.
# ==============================================================================

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore

import config

logger = logging.getLogger("crypto_bot.firebase")

# ==============================================================================
# FIREBASE ADMIN SDK INITIALIZATION
# ==============================================================================
# Initializes the Firestore database client. If credential parsing fails, it 
# defaults to dummy behavior or logs errors clearly without throwing raw traces.

db: Optional[Any] = None

try:
    if config.FIREBASE_CREDENTIALS:
        # Load the credentials from environment variable JSON string
        cred_dict = json.loads(config.FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("[+] Firebase Admin SDK successfully initialized.")
    else:
        logger.warning("[!] FIREBASE_CREDENTIALS not set. Firestore operations will fail or operate in Mock mode.")
except Exception as e:
    logger.error(f"[X] Failed to initialize Firebase Admin SDK. Error: {str(e)}")
    db = None

# ==============================================================================
# DATA ACCESS INTERFACE
# ==============================================================================

def get_settings() -> Dict[str, Any]:
    """
    Retrieves global trading settings from /config/settings document in Firestore.
    If the document does not exist, returns safe defaults.
    
    Accepts:
        None
    Returns:
        Dict[str, Any]: Configuration settings containing 'mode', 'pairs', etc.
    """
    default_settings = {
        "mode": "paper",
        "pairs": config.DEFAULT_PAIRS,
        "risk_per_trade": config.RISK_PER_TRADE,
        "max_open_trades": config.MAX_OPEN_TRADES,
    }
    
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Returning default local configurations.")
        return default_settings

    try:
        doc_ref = db.collection("config").document("settings")
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            # NOTE: Validate and merge defaults to avoid missing expected fields
            for key, val in default_settings.items():
                if key not in data:
                    data[key] = val
            return data
        else:
            # Seed default config to Firestore for the user if it doesn't exist
            logger.info("[-] /config/settings document not found. Seeding default configurations.")
            doc_ref.set(default_settings)
            return default_settings
    except Exception as e:
        logger.error(f"[X] Error fetching trading settings from Firestore: {str(e)}. Using fallback defaults.")
        return default_settings


def get_paper_balance() -> float:
    """
    Retrieves simulated USDT paper trading balance from /paper_balance/state doc.
    If the balance document does not exist, initializes it to $10.00 USDT.
    
    Accepts:
        None
    Returns:
        float: Available paper USDT balance.
    """
    default_balance = 10.00
    
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Returning mock paper balance.")
        return default_balance

    try:
        doc_ref = db.collection("paper_balance").document("state")
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            return float(data.get("usdt", default_balance))
        else:
            logger.info("[-] /paper_balance/state document not found. Seeding initial $10.00 USDT balance.")
            doc_ref.set({
                "usdt": default_balance,
                "last_updated": firestore.SERVER_TIMESTAMP
            })
            return default_balance
    except Exception as e:
        logger.error(f"[X] Error getting paper balance: {str(e)}. Using fallback balance.")
        return default_balance


def update_paper_balance(new_balance: float) -> bool:
    """
    Updates the paper USDT balance in Firestore.
    
    Accepts:
        new_balance (float): The newly computed paper balance value.
    Returns:
        bool: True if successfully updated, False otherwise.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Mock mode: Balance update skipped.")
        return False

    try:
        # Prevent negative balance allocation
        sanitized_balance = max(0.0, float(new_balance))
        doc_ref = db.collection("paper_balance").document("state")
        doc_ref.set({
            "usdt": sanitized_balance,
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)
        logger.info(f"[+] Updated paper trading balance to: ${sanitized_balance:.2f} USDT")
        return True
    except Exception as e:
        logger.error(f"[X] Failed to update paper balance in Firestore: {str(e)}")
        return False


def log_trade(trade: Dict[str, Any]) -> Optional[str]:
    """
    Saves a new open or closed trade structure into /trades collection.
    
    Accepts:
        trade (dict): Complete dictionary of trade variables (pair, entry price, etc.).
    Returns:
        Optional[str]: Generated document ID if success, None if failure.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Mock mode: Trade log skipped.")
        return "mock_trade_id_123"

    try:
        # Enforce server-side timestamp to maintain accurate ordering
        trade_data = trade.copy()
        trade_data["timestamp"] = firestore.SERVER_TIMESTAMP
        
        # Add to the trades collection
        ref = db.collection("trades").document()
        ref.set(trade_data)
        logger.info(f"[+] Logged trade for {trade.get('pair')} action {trade.get('action')} to Firestore. Doc ID: {ref.id}")
        return ref.id
    except Exception as e:
        logger.error(f"[X] Failed to write trade log to Firestore: {str(e)}")
        return None


def get_open_trades() -> List[Dict[str, Any]]:
    """
    Fetches list of all trades in Firestore where status is 'open'.
    
    Accepts:
        None
    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing the open trades.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Returning empty open trades.")
        return []

    try:
        trades_ref = db.collection("trades")
        query = trades_ref.where("status", "==", "open").stream()
        
        open_trades = []
        for doc in query:
            trade = doc.to_dict()
            trade["id"] = doc.id
            open_trades.append(trade)
        return open_trades
    except Exception as e:
        logger.error(f"[X] Failed to retrieve open trades: {str(e)}")
        return []


def close_trade(trade_id: str, pnl: float, exit_price: float) -> bool:
    """
    Updates an open trade's status to 'closed' and sets exit metrics.
    
    Accepts:
        trade_id (str): Document ID of the trade.
        pnl (float): Realized profit and loss.
        exit_price (float): Price the asset was sold/bought back at.
    Returns:
        bool: True if transaction succeeds, False otherwise.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Mock close skipped.")
        return False

    try:
        doc_ref = db.collection("trades").document(trade_id)
        doc_ref.set({
            "status": "closed",
            "pnl": pnl,
            "exit_price": exit_price,
            "closed_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        logger.info(f"[+] Successfully closed trade document ID: {trade_id}")
        return True
    except Exception as e:
        logger.error(f"[X] Failed to close trade {trade_id} in Firestore: {str(e)}")
        return False


def get_last_stop_loss_time() -> Optional[datetime]:
    """
    Queries the trades collection to find the most recent trade closed due to a stop loss.
    This is used to determine if the bot is within the cooldown cycle window.
    
    Accepts:
        None
    Returns:
        Optional[datetime]: Datetime of the last stop loss hit, or None.
    """
    if db is None:
        return None

    try:
        trades_ref = db.collection("trades")
        # Fetch the closed trades without ordering in Firestore to avoid index errors
        query = trades_ref.where("status", "==", "closed").limit(50).stream()
        
        closed_trades = []
        for doc in query:
            trade = doc.to_dict()
            closed_trades.append(trade)

        # Helper function to parse close timestamp safely for sorting
        def get_close_time(t: Dict[str, Any]) -> datetime:
            cat = t.get("closed_at")
            if isinstance(cat, datetime):
                # Ensure timezone awareness
                if cat.tzinfo is None:
                    return cat.replace(tzinfo=timezone.utc)
                return cat
            elif isinstance(cat, str):
                try:
                    return datetime.fromisoformat(cat.replace("Z", "+00:00"))
                except ValueError:
                    pass
            # Default minimum timestamp if none exists
            return datetime.min.replace(tzinfo=timezone.utc)

        # Sort the closed trades by closed_at descending in memory
        closed_trades.sort(key=get_close_time, reverse=True)
        
        for trade in closed_trades:
            # If the trade was a loss, classify it as a stop_loss trigger event
            pnl = trade.get("pnl", 0.0)
            if pnl < 0:
                closed_at = trade.get("closed_at")
                if isinstance(closed_at, datetime):
                    return closed_at
                elif isinstance(closed_at, str):
                    try:
                        return datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                    except ValueError:
                        pass
        return None
    except Exception as e:
        logger.error(f"[X] Failed to query last stop loss time: {str(e)}")
        return None


def update_daily_performance(date_str: str, pnl_to_add: float, is_win: bool) -> bool:
    """
    Aggregates trade performance stats for a specific day.
    
    Accepts:
        date_str (str): Date formatted as YYYY-MM-DD.
        pnl_to_add (float): profit or loss to aggregate.
        is_win (bool): Whether this trade was closed at a profit.
    Returns:
        bool: True if updated successfully, False otherwise.
    """
    if db is None:
        return False

    try:
        doc_ref = db.collection("performance").document(date_str)
        
        # Transaction-based atomic update to avoid race conditions
        @firestore.transactional
        def update_in_transaction(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                total_trades = data.get("total_trades", 0) + 1
                wins = data.get("wins", 0) + (1 if is_win else 0)
                losses = data.get("losses", 0) + (0 if is_win else 1)
                total_pnl = float(data.get("total_pnl", 0.0)) + pnl_to_add
                win_rate = wins / total_trades if total_trades > 0 else 0.0
                
                transaction.update(ref, {
                    "total_trades": total_trades,
                    "wins": wins,
                    "losses": losses,
                    "total_pnl": total_pnl,
                    "win_rate": win_rate,
                    "last_updated": firestore.SERVER_TIMESTAMP
                })
            else:
                transaction.set(ref, {
                    "total_trades": 1,
                    "wins": 1 if is_win else 0,
                    "losses": 0 if is_win else 1,
                    "total_pnl": pnl_to_add,
                    "win_rate": 1.0 if is_win else 0.0,
                    "last_updated": firestore.SERVER_TIMESTAMP
                })
        
        transaction = db.transaction()
        update_in_transaction(transaction, doc_ref)
        logger.info(f"[+] Daily performance aggregated for date: {date_str}")
        return True
    except Exception as e:
        logger.error(f"[X] Failed to update daily performance stats: {str(e)}")
        return False


def log_sweep(sweep_data: Dict[str, Any]) -> None:
    """
    Logs a bot sweep cycle to /sweeps collection and maintains only the 10 most recent sweeps to conserve storage.
    
    Accepts:
        sweep_data (dict): Complete sweep cycle execution report containing scanned pairs, sentiment, etc.
    Returns:
        None
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Skipping logging sweep to database.")
        return

    try:
        # Enforce server-side timestamp for accuracy
        sweep_record = sweep_data.copy()
        sweep_record["timestamp"] = firestore.SERVER_TIMESTAMP
        
        # Save to sweeps collection
        ref = db.collection("sweeps").document()
        ref.set(sweep_record)
        logger.info(f"[+] Logged sweep details to Firestore. Doc ID: {ref.id}")

        # Keep only the 10 most recent sweeps to prevent unlimited storage growth
        sweeps = db.collection("sweeps").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        count = 0
        for doc in sweeps:
            count += 1
            if count > 10:
                # Delete older document
                db.collection("sweeps").document(doc.id).delete()
                
    except Exception as e:
        logger.error(f"[X] Failed to log sweep to Firestore: {str(e)}")


def get_recent_sweeps(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieves the most recent execution sweeps from Firestore.
    
    Accepts:
        limit (int): The maximum number of sweeps to retrieve (default 10).
    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing the recent sweeps.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Returning empty list for sweeps.")
        return []

    try:
        query = db.collection("sweeps").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        recent = []
        for doc in query:
            data = doc.to_dict()
            data["id"] = doc.id
            if "timestamp" in data and hasattr(data["timestamp"], "isoformat"):
                data["timestamp"] = data["timestamp"].isoformat()
            recent.append(data)
        return recent
    except Exception as e:
        logger.error(f"[X] Failed to fetch recent sweeps from Firestore: {str(e)}")
        return []


def get_all_trades(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves all trades (both open and closed) from Firestore.
    
    Accepts:
        limit (int): The maximum number of trades to fetch (default 50).
    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing the trades.
    """
    if db is None:
        logger.warning("[!] Firestore db is uninitialized. Returning empty trades.")
        return []

    try:
        trades_ref = db.collection("trades")
        query = trades_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        
        trades = []
        for doc in query:
            trade = doc.to_dict()
            trade["id"] = doc.id
            if "timestamp" in trade and hasattr(trade["timestamp"], "isoformat"):
                trade["timestamp"] = trade["timestamp"].isoformat()
            if "closed_at" in trade and hasattr(trade["closed_at"], "isoformat"):
                trade["closed_at"] = trade["closed_at"].isoformat()
            trades.append(trade)
        return trades
    except Exception as e:
        logger.error(f"[X] Failed to retrieve all trades: {str(e)}")
        return []



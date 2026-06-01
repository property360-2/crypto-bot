# ==============================================================================
# File: main.py
# Purpose: FastAPI web server application containing the API endpoints and the
#          bot's main run loop execution pipeline.
# Fits into: Main Orchestrator. Glues core decision logic, data clients, and routes.
# ==============================================================================

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Header, Query, status

import config
from data import firebase_client, exchange_client
from strategies import momentum, sentiment, arbitrage
from core import signal_combiner, risk_manager, executor
from utils import logger as bot_logger, telegram_alerts

# ==============================================================================
# SETUP RUNTIME DIAGNOSTICS LOGGING
# ==============================================================================
bot_logger.setup_logging()
logger = logging.getLogger("crypto_bot.main")

# Instantiate FastAPI application
app = FastAPI(
    title="Crypto Trading Bot",
    description="Multi-Strategy Algorithmic Crypto Paper-Trading Engine",
    version="1.0.0"
)

# In-memory execution lock to avoid parallel overlapping /run triggers
run_lock = asyncio.Lock()

# ==============================================================================
# HEALTH CHECK ROUTE
# ==============================================================================

@app.get("/", status_code=status.HTTP_200_OK)
def read_root() -> Dict[str, Any]:
    """
    Exposes a lightweight, simple endpoint to test server responsiveness.
    Acts as target check for cron-job.org or Render warm up keep-alives.
    
    Accepts:
        None
    Returns:
        Dict[str, Any]: System check response package.
    """
    logger.info("[-] Health check endpoint triggered.")
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": config.ENVIRONMENT,
        "message": "Algorithmic bot online and ready."
    }

# ==============================================================================
# TELEMETRY STATUS ROUTE
# ==============================================================================

@app.get("/status", status_code=status.HTTP_200_OK)
def get_status() -> Dict[str, Any]:
    """
    Exposes telemetry metrics regarding paper balance, active positions, 
    and general configuration settings stored in the database.
    
    Accepts:
        None
    Returns:
        Dict[str, Any]: Data metrics summary block.
    """
    try:
        settings = firebase_client.get_settings()
        balance = firebase_client.get_paper_balance()
        open_trades = firebase_client.get_open_trades()
        last_sl = firebase_client.get_last_stop_loss_time()
        
        # Clean timestamps in trades for JSON response
        formatted_trades = []
        for trade in open_trades:
            t_copy = trade.copy()
            if "timestamp" in t_copy and hasattr(t_copy["timestamp"], "isoformat"):
                t_copy["timestamp"] = t_copy["timestamp"].isoformat()
            formatted_trades.append(t_copy)

        return {
            "mode": settings.get("mode", "paper"),
            "target_pairs": settings.get("pairs", []),
            "paper_balance_usdt": balance,
            "active_positions_count": len(open_trades),
            "open_positions": formatted_trades,
            "last_stop_loss_time": last_sl.isoformat() if last_sl else None,
            "in_cooldown": risk_manager.is_in_cooldown(last_sl),
            "latest_sentiment": settings.get("latest_sentiment", {"fear_and_greed": 50, "news_score": 0.0}),
            "recent_sweeps": firebase_client.get_recent_sweeps(limit=5),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[X] Exception loading status details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error loading status telemetry. Check server diagnostic logs."
        )

# ==============================================================================
# TRADED LIST ROUTE
# ==============================================================================

@app.get("/traded", status_code=status.HTTP_200_OK)
def get_traded_list(limit: int = Query(50, description="Max number of trades to fetch")) -> List[Dict[str, Any]]:
    """
    Exposes a history of all executed trades (both open and closed positions).
    
    Accepts:
        limit (int): The maximum number of trade documents to fetch.
    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing the trades.
    """
    try:
        logger.info(f"[-] Fetching list of all traded assets (limit={limit}).")
        trades = firebase_client.get_all_trades(limit=limit)
        return trades
    except Exception as e:
        logger.error(f"[X] Exception loading traded list details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error loading traded list: {str(e)}"
        )

# ==============================================================================
# WAITED LIST ROUTE
# ==============================================================================

@app.get("/waited", status_code=status.HTTP_200_OK)
def get_waited_list(limit: int = Query(20, description="Max number of wait sweeps to fetch")) -> List[Dict[str, Any]]:
    """
    Exposes a history of all sweep cycles where the bot evaluated the markets
    but decided to WAIT (no trade opened).
    
    Accepts:
        limit (int): The maximum number of wait cycles to fetch.
    Returns:
        List[Dict[str, Any]]: Filtered wait cycle execution logs.
    """
    try:
        logger.info(f"[-] Fetching recent wait sweeps (limit={limit}).")
        sweeps = firebase_client.get_recent_sweeps(limit=limit * 2) # Fetch extra to account for any that opened a trade
        
        waits = []
        for sweep in sweeps:
            scanned_pairs = sweep.get("scanned_pairs", {})
            if not scanned_pairs:
                continue
                
            # Check if this sweep resulted in any trade opened
            has_trade = any(
                "TRADE_OPENED" in str(details.get("execution", ""))
                for details in scanned_pairs.values()
            )
            
            # If no trades were opened during this entire sweep, it counts as a wait cycle!
            if not has_trade:
                wait_entry = {
                    "timestamp": sweep.get("timestamp"),
                    "global_sentiment": sweep.get("global_sentiment", {}),
                    "reasons": {}
                }
                
                for pair, details in scanned_pairs.items():
                    wait_entry["reasons"][pair] = {
                        "action": details.get("action"),
                        "signal_score": details.get("signal_score"),
                        "spot_price": details.get("spot_price"),
                        "reasons": details.get("reasons", [])
                    }
                
                waits.append(wait_entry)
                if len(waits) >= limit:
                    break
                    
        return waits
    except Exception as e:
        logger.error(f"[X] Exception loading waited list details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error loading waited list: {str(e)}"
        )

# ==============================================================================
# CONFIG TOGGLE ROUTE
# ==============================================================================

@app.get("/toggle", status_code=status.HTTP_200_OK)
def toggle_mode(
    mode: str = Query(..., description="'paper' or 'live'"),
    api_key: str = Query(..., description="API Security verification key")
) -> Dict[str, Any]:
    """
    Switches system execution settings between paper and live trading in Firestore.
    Protected by simple API verification keys.
    
    Accepts:
        mode (str): Destination environment target ('paper' or 'live').
        api_key (str): Security passcode to authorize changes.
    Returns:
        Dict[str, Any]: Confirmation success block.
    """
    # NOTE: Enforce protection gate matching Binance secret to avoid unauthorized access.
    # If standard config secret is empty, fall back to simple default local validation passcode
    passcode = config.BINANCE_SECRET if config.BINANCE_SECRET else "antigravity-passcode"
    
    if api_key != passcode:
        logger.warning("[!] Unauthorized toggle attempt rejected.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized configuration action. Invalid api_key credentials."
        )

    if mode not in ["paper", "live"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mode setting choice. Select either 'paper' or 'live'."
        )

    # NOTE: Phase 1 is paper only. Let live changes set but log warnings.
    try:
        if firebase_client.db is None:
            logger.warning("[!] Firestore db is uninitialized. Simulated toggle mode update in progress.")
            return {
                "status": "success",
                "message": f"Firestore is uninitialized. Local simulated toggle set to: {mode}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        settings_ref = firebase_client.db.collection("config").document("settings")
        settings_ref.set({"mode": mode}, merge=True)
        logger.info(f"[+] Trading execution environment updated to: {mode}")
        return {
            "status": "success",
            "message": f"Trading environment successfully changed to: {mode}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[X] Exception updating trading mode configuration in Firestore: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Database update error: {str(e)}"
        )

# ==============================================================================
# CORE BOT MAIN CYCLE LOOP
# ==============================================================================

@app.get("/run", status_code=status.HTTP_200_OK)
async def run_bot_cycle() -> Dict[str, Any]:
    """
    Central loop pipeline triggered by cron-job every 5 minutes.
    Performs price scans, triggers SL/TP check sweeps, runs indicators, 
    and executes orders. Protected by concurrency lock to avoid overlaps.
    
    Accepts:
        None
    Returns:
        Dict[str, Any]: Execution loop transaction logs summary.
    """
    # 1. Acquire execution lock to prevent parallel runs
    if run_lock.locked():
        logger.warning("[!] Concurrency lock active. Parallel execution attempt blocked.")
        return {
            "status": "busy",
            "message": "Execution loop currently busy processing another pipeline. Trigger skipped.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async with run_lock:
        logger.info("================================================================")
        logger.info("[*] STARTING BOT ANALYSIS & TRADE EXECUTION CYCLE...")
        logger.info("================================================================")
        
        cycle_start = datetime.now(timezone.utc)
        execution_report: Dict[str, Any] = {
            "status": "completed",
            "timestamp": cycle_start.isoformat(),
            "closed_trades": [],
            "scanned_pairs": {},
            "errors": []
        }

        try:
            # 2. Load configurations and pairs list
            settings = firebase_client.get_settings()
            pairs = settings.get("pairs", config.DEFAULT_PAIRS)
            
            logger.info(f"[-] Loaded target trading pairs to scan: {pairs}")

            # 3. Gather current price ticker details for all pairs
            current_prices: Dict[str, float] = {}
            for pair in pairs:
                price = exchange_client.fetch_current_price(pair)
                if price > 0.0:
                    current_prices[pair] = price
            
            # 4. Sweep open positions against stop-loss and take-profit targets
            closed_trades = executor.check_open_trades(current_prices)
            if closed_trades:
                execution_report["closed_trades"] = [t["id"] for t in closed_trades]
                # Send immediate alert notices for exits
                for t in closed_trades:
                    alert_text = telegram_alerts.format_trade_alert(t)
                    await telegram_alerts.send_alert(alert_text)

            # 5. Fetch Global Sentiment Metrics (Fear & Greed Index + News) once per loop
            # This is highly efficient and saves significant API lookups
            sentiment_rep = sentiment.analyze()
            fng_score = sentiment_rep.get("indicators", {}).get("fear_and_greed", 50)
            execution_report["global_sentiment"] = {
                "fear_and_greed": fng_score,
                "news_score": sentiment_rep.get("indicators", {}).get("news_score", 0.0)
            }
            # Save to firestore for status route access if database is initialized and active
            if firebase_client.db is not None:
                try:
                    firebase_client.db.collection("config").document("settings").set({"latest_sentiment": execution_report["global_sentiment"]}, merge=True)
                except Exception as db_err:
                    logger.error(f"[X] Failed to cache sentiment in Firestore: {str(db_err)}")
            else:
                logger.warning("[!] Firestore db is uninitialized. Skipping news/F&G sentiment caching to db.")

            # 6. Scan markets and execute strategy indicators for each pair
            for pair in pairs:
                try:
                    price = current_prices.get(pair)
                    if not price or price <= 0.0:
                        logger.warning(f"[!] Skipping strategy analysis for {pair} due to invalid price detail.")
                        continue

                    # Fetch candlestick series
                    df = exchange_client.fetch_ohlcv(
                        pair, 
                        timeframe=config.CANDLE_TIMEFRAME, 
                        limit=config.CANDLE_LOOKBACK
                    )
                    
                    if df.empty or len(df) < 50:
                        logger.warning(f"[!] Strategy skipped for {pair}. Insufficient historical bars.")
                        continue

                    # Run strategies indicators
                    momentum_rep = momentum.analyze(df)
                    arbitrage_rep = arbitrage.analyze(pair)

                    # Compute combined signal report
                    combined_rep = signal_combiner.combine_signals(
                        momentum_rep, sentiment_rep, arbitrage_rep
                    )

                    # Log scanner signals to report
                    execution_report["scanned_pairs"][pair] = {
                        "action": combined_rep.get("action"),
                        "signal_score": combined_rep.get("final_signal"),
                        "rsi": momentum_rep.get("indicators", {}).get("rsi"),
                        "spot_price": price,
                        "futures_price": arbitrage_rep.get("indicators", {}).get("futures_price", price),
                        "reasons": combined_rep.get("reasons", [])
                    }

                    # Trigger trade execution checks (Passing F&G index for extreme fear governance)
                    opened_trade = executor.execute_signal(pair, combined_rep, price, fng_score)
                    if opened_trade:
                        # Send alert on Telegram
                        alert_text = telegram_alerts.format_trade_alert(opened_trade)
                        await telegram_alerts.send_alert(alert_text)
                        execution_report["scanned_pairs"][pair]["execution"] = f"TRADE_OPENED (Doc: {opened_trade.get('id')})"
                    else:
                        execution_report["scanned_pairs"][pair]["execution"] = "NO_TRADE (Signal neutral or blocked by risk gates)"
                        
                except Exception as pair_error:
                    err_msg = f"Error processing market pair {pair}: {str(pair_error)}"
                    logger.error(f"[X] {err_msg}")
                    execution_report["errors"].append(err_msg)

            cycle_end = datetime.now(timezone.utc)
            duration = (cycle_end - cycle_start).total_seconds()
            logger.info(f"[+] CYCLE EXECUTION COMPLETED in {duration:.2f} seconds.")
            logger.info("================================================================")
            
            # Log sweep results to Firestore for status tracking
            firebase_client.log_sweep(execution_report)
            
            return execution_report

        except Exception as system_error:
            err_msg = f"Critical bot loop pipeline execution crash: {str(system_error)}"
            logger.critical(f"[X] {err_msg}")
            execution_report["status"] = "failed"
            execution_report["errors"].append(err_msg)
            
            # Send high priority system crash alerts to Telegram
            await telegram_alerts.send_alert(f"🚨 *[SYSTEM CRITICAL]* Crypto Bot loop crashed: `{str(system_error)}`")
            
            return execution_report

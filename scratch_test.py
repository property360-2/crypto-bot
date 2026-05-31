# ==============================================================================
# File: scratch_test.py
# Purpose: Comprehensive Phase 2 verification and unit testing suite for the 
#          Crypto Trading Bot. Mocks Firestore db, CryptoPanic news feeds, 
#          Alternative.me Fear & Greed API, and CCXT exchange prices to validate 
#          local technical indicator engines, arbitrage calculators, sentiment 
#          scoring filters, meta-signal confluence combiner, risk gates 
#          (specifically Extreme Fear constraints), and paper executors.
# Fits into: Quality Assurance and Local Logic Verification component.
# ==============================================================================

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

# Ensure our local bot packages are discoverable in Python sys path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure diagnostics logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) : %(message)s")
logger = logging.getLogger("crypto_bot.tests")

# ==============================================================================
# FIRESTORE MOCK SYSTEM
# ==============================================================================
# Mock Firebase Admin SDK before loading other bot modules to intercept imports

class DummyDocument:
    """
    Mock representing a Firestore DocumentSnapshot object.
    
    Accepts:
        exists (bool): Whether the document exists in Firestore.
        data (Dict[str, Any]): The key-value fields of the document.
        id (str): The document ID string.
    """
    def __init__(self, exists: bool = True, data: Optional[Dict[str, Any]] = None, id: str = "mock_doc_id"):
        self.exists = exists
        self._data = data or {}
        self.id = id
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Returns the data dictionary of the document.
        """
        return self._data
        
    def get(self, transaction: Optional[Any] = None) -> "DummyDocument":
        """
        Mock document get method. Returns itself.
        """
        return self
        
    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        """
        Mock document set method. Updates data in memory.
        """
        self._data.update(data)
        
    def update(self, data: Dict[str, Any]) -> None:
        """
        Mock document update method. Updates data in memory.
        """
        self._data.update(data)

class DummyCollection:
    """
    Mock representing a Firestore CollectionReference object.
    
    Accepts:
        name (str): The collection path name in Firestore.
    """
    def __init__(self, name: str):
        self.name = name
        
    def document(self, id: Optional[str] = "mock_doc_id") -> DummyDocument:
        """
        Simulates retrieving a document reference from the collection.
        Returns pre-populated settings or balance data based on collection paths.
        
        Accepts:
            id (str, optional): The document ID.
        Returns:
            DummyDocument: Loaded dummy document.
        """
        if self.name == "config" and id == "settings":
            return DummyDocument(
                exists=True, 
                data={"mode": "paper", "usdt": 100.0, "pairs": ["BTC/USDT", "ETH/USDT"], "risk_per_trade": 0.10, "max_open_trades": 2}, 
                id=id
            )
        elif self.name == "paper_balance" and id == "state":
            return DummyDocument(exists=True, data={"usdt": 100.0}, id=id)
        elif self.name == "performance":
            return DummyDocument(exists=True, data={"total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}, id=id)
        
        # Default empty document
        return DummyDocument(exists=True, data={}, id=id or "mock_doc_id")
        
    def where(self, *args, **kwargs) -> "DummyCollection":
        """
        Simulates where query filtering. Returns itself.
        """
        return self
        
    def order_by(self, *args, **kwargs) -> "DummyCollection":
        """
        Simulates sorting query. Returns itself.
        """
        return self
        
    def limit(self, *args, **kwargs) -> "DummyCollection":
        """
        Simulates limit constraints. Returns itself.
        """
        return self
        
    def stream(self) -> List[DummyDocument]:
        """
        Simulates streaming query results. Returns empty active positions by default.
        """
        return []

class DummyDB:
    """
    Mock representing a Firestore Client object.
    """
    def collection(self, name: str) -> DummyCollection:
        """
        Simulates getting a collection from Firestore.
        
        Accepts:
            name (str): The collection name.
        Returns:
            DummyCollection: Instantiated mock collection.
        """
        return DummyCollection(name)
        
    def transaction(self) -> Any:
        """
        Simulates an atomic transaction manager.
        """
        class Transaction:
            def update(self, *args, **kwargs): pass
            def set(self, *args, **kwargs): pass
        return Transaction()

# Inject Mock DB instance into firebase_client BEFORE loading strategies and core
import data.firebase_client as fc
fc.db = DummyDB()

# Now import the modules under test safely
from strategies import momentum, sentiment, arbitrage
from core import signal_combiner, risk_manager, executor
import data.exchange_client as ec
import strategies.sentiment as ss

# ==============================================================================
# MOCK MARKET DATA GENERATORS
# ==============================================================================

def generate_mock_market_data(trend: str = "bullish", length: int = 100) -> pd.DataFrame:
    """
    Generates simulated candlestick OHLCV DataFrame for strategy testing.
    Uses '5min' frequency instead of deprecated '5T' to prevent pandas 2.2 errors.
    
    Accepts:
        trend (str): Direction pattern ('bullish', 'bearish', 'flat').
        length (int): Candle counts.
    Returns:
        pd.DataFrame: Pandas DataFrame populated with historical bar variables.
    """
    np.random.seed(42)
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=length, freq="5min")
    
    close_prices = []
    current_price = 50000.0
    
    for i in range(length):
        if trend == "bullish":
            change = np.random.normal(50.0, 100.0)
        elif trend == "bearish":
            change = np.random.normal(-50.0, 100.0)
        else:
            change = np.random.normal(0.0, 100.0)
            
        current_price += change
        close_prices.append(current_price)
        
    df = pd.DataFrame({
        "open": [p - np.random.uniform(5, 20) for p in close_prices],
        "high": [p + np.random.uniform(10, 30) for p in close_prices],
        "low": [p - np.random.uniform(10, 30) for p in close_prices],
        "close": close_prices,
        "volume": [np.random.uniform(1, 5) for _ in close_prices]
    }, index=timestamps)
    
    df.index.name = "timestamp"
    return df

# ==============================================================================
# TEST RUNNER LOGIC
# ==============================================================================

def run_tests() -> None:
    """
    Main unit testing suite executor. Orchestrates multiple tests validating momentum, 
    arbitrage premium maps, news/F&G sentiment, weighted signal combining confluences, 
    extreme fear blocks, and paper execution flows.
    
    Accepts:
        None
    Returns:
        None
    """
    logger.info("=== STARTING COMPREHENSIVE PHASE 2 STRATEGY & LOGIC UNIT TESTS ===")
    
    success = True
    
    # --------------------------------------------------------------------------
    # Test 1: Momentum Strategy Technical Indicator Calculations (Bullish Trend)
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 1] Testing Momentum Strategy Indicators on Bullish Data...")
        bullish_df = generate_mock_market_data("bullish", 100)
        report = momentum.analyze(bullish_df)
        
        logger.info(f"-> Action recommended: {report.get('action')}")
        logger.info(f"-> Momentum Signal score: {report.get('signal')}")
        logger.info(f"-> RSI-14 calculation result: {report.get('indicators', {}).get('rsi'):.2f}")
        logger.info(f"-> EMA20={report.get('indicators', {}).get('ema_20'):.2f}, EMA50={report.get('indicators', {}).get('ema_50'):.2f}")
        
        # Verify columns are calculated and present
        assert report.get("signal") is not None
        assert "rsi" in report.get("indicators", {})
        assert "macd" in report.get("indicators", {})
        assert report.get("indicators", {}).get("ema_20") > 0.0
        logger.info("[Test 1] PASSED.")
    except Exception as e:
        logger.error(f"[Test 1] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # Test 2: Arbitrage Premium Spread Strategy Mapper
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 2] Testing Binance Spot vs USD-M Futures Arbitrage Premium...")
        
        # Case 2A: Contango Market (Futures > Spot by >= 0.3%)
        ec.fetch_current_price = lambda pair: 50000.0
        ec.fetch_futures_price = lambda pair: 50200.0  # (50200 - 50000) / 50000 = +0.40% Premium
        
        contango_rep = arbitrage.analyze("BTC/USDT")
        logger.info(f"-> Contango Case Signal: {contango_rep.get('signal')} | Action: {contango_rep.get('action')} | Premium: {contango_rep.get('indicators', {}).get('premium_pct')}%")
        assert contango_rep.get("signal") == 0.5
        assert contango_rep.get("action") == "BUY"
        
        # Case 2B: Backwardation Market (Futures < Spot by <= -0.1%)
        ec.fetch_current_price = lambda pair: 50000.0
        ec.fetch_futures_price = lambda pair: 49900.0  # (49900 - 50000) / 50000 = -0.20% Premium
        
        backwardation_rep = arbitrage.analyze("BTC/USDT")
        logger.info(f"-> Backwardation Case Signal: {backwardation_rep.get('signal')} | Action: {backwardation_rep.get('action')} | Premium: {backwardation_rep.get('indicators', {}).get('premium_pct')}%")
        assert backwardation_rep.get("signal") == -0.5
        assert backwardation_rep.get("action") == "SELL"
        
        # Case 2C: Neutral Market (Premium between -0.1% and +0.3%)
        ec.fetch_current_price = lambda pair: 50000.0
        ec.fetch_futures_price = lambda pair: 50050.0  # +0.10% Premium
        
        neutral_rep = arbitrage.analyze("BTC/USDT")
        logger.info(f"-> Neutral Case Signal: {neutral_rep.get('signal')} | Action: {neutral_rep.get('action')} | Premium: {neutral_rep.get('indicators', {}).get('premium_pct')}%")
        assert neutral_rep.get("signal") == 0.0
        assert neutral_rep.get("action") == "HOLD"
        
        logger.info("[Test 2] PASSED.")
    except Exception as e:
        logger.error(f"[Test 2] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # Test 3: Sentiment Strategy Headline & F&G Score Aggregator
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 3] Testing Sentiment Strategy Headline Parsing & F&G Aggregator...")
        
        # Case 3A: Greed Index + Bullish News headlines
        ss._fetch_fear_and_greed_score = lambda: 80
        ss._fetch_cryptopanic_news = lambda: [
            "Bitcoin breakout with strong pump",
            "Ethereum rise with massive green bullish candle",
            "SOL support grows as buyers rally long"
        ]
        
        bullish_sent = sentiment.analyze()
        logger.info(f"-> Bullish Sentiment Case Signal: {bullish_sent.get('signal')} | Action: {bullish_sent.get('action')} | Headlines parsed: {bullish_sent.get('indicators', {}).get('news_headlines_count')}")
        # F&G mapped = 0.5. Local keywords scored positives. Combined should be strongly positive.
        assert bullish_sent.get("signal") >= 0.3
        assert bullish_sent.get("action") == "BUY"
        
        # Case 3B: Fear Index + Bearish News headlines
        ss._fetch_fear_and_greed_score = lambda: 15
        ss._fetch_cryptopanic_news = lambda: [
            "Bitcoin dump with massive crash",
            "Ethereum drop as bearish panic grows",
            "SOL sell pressure rejects at resistance"
        ]
        
        bearish_sent = sentiment.analyze()
        logger.info(f"-> Bearish Sentiment Case Signal: {bearish_sent.get('signal')} | Action: {bearish_sent.get('action')} | Headlines parsed: {bearish_sent.get('indicators', {}).get('news_headlines_count')}")
        # F&G mapped = -0.5. News score negative. Combined negative.
        assert bearish_sent.get("signal") <= -0.3
        assert bearish_sent.get("action") == "SELL"
        
        logger.info("[Test 3] PASSED.")
    except Exception as e:
        logger.error(f"[Test 3] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # Test 4: Meta-Signal Combiner Weighted Confluence Matrix
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 4] Testing Meta-Signal Combiner Weighted Score Matrix...")
        
        # Base Confluence Weights: Momentum=35%, Sentiment=35%, Arbitrage=30%
        # Case 4A: Strong BUY confluence (Score >= 0.60)
        # Momentum signal = 0.80, Sentiment = 0.60, Arbitrage = 0.50
        # Expected score: 0.8 * 0.35 + 0.6 * 0.35 + 0.5 * 0.3 = 0.28 + 0.21 + 0.15 = 0.64
        mom_rep = {"signal": 0.8, "action": "BUY"}
        sent_rep = {"signal": 0.6, "action": "BUY"}
        arb_rep = {"signal": 0.5, "action": "BUY"}
        
        combined_buy = signal_combiner.combine_signals(mom_rep, sent_rep, arb_rep)
        logger.info(f"-> Buy Confluence: Score={combined_buy.get('final_signal')} | Action={combined_buy.get('action')}")
        assert combined_buy.get("action") == "STRONG_BUY"
        assert abs(combined_buy.get("final_signal") - 0.64) < 0.02
        
        # Case 4B: Strong SELL confluence (Score <= -0.60)
        # Momentum signal = -0.80, Sentiment = -0.60, Arbitrage = -0.50
        # Expected score: -0.64
        mom_rep = {"signal": -0.8, "action": "SELL"}
        sent_rep = {"signal": -0.6, "action": "SELL"}
        arb_rep = {"signal": -0.5, "action": "SELL"}
        
        combined_sell = signal_combiner.combine_signals(mom_rep, sent_rep, arb_rep)
        logger.info(f"-> Sell Confluence: Score={combined_sell.get('final_signal')} | Action={combined_sell.get('action')}")
        assert combined_sell.get("action") == "STRONG_SELL"
        assert abs(combined_sell.get("final_signal") - (-0.64)) < 0.02
        
        # Case 4C: Neutral / HOLD confluence
        # Momentum = 0.2, Sentiment = 0.1, Arbitrage = 0.0
        # Expected: 0.2 * 0.35 + 0.1 * 0.35 = 0.07 + 0.035 = 0.105 -> Action HOLD
        mom_rep = {"signal": 0.2, "action": "HOLD"}
        sent_rep = {"signal": 0.1, "action": "HOLD"}
        arb_rep = {"signal": 0.0, "action": "HOLD"}
        
        combined_hold = signal_combiner.combine_signals(mom_rep, sent_rep, arb_rep)
        logger.info(f"-> Hold Confluence: Score={combined_hold.get('final_signal')} | Action={combined_hold.get('action')}")
        assert combined_hold.get("action") == "HOLD"
        assert abs(combined_hold.get("final_signal") - 0.11) < 0.02
        
        logger.info("[Test 4] PASSED.")
    except Exception as e:
        logger.error(f"[Test 4] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # Test 5: Risk Manager Governance Gates & Extreme Fear Restriction
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 5] Testing Risk Manager Gates & Extreme Fear Governance...")
        balance = 100.0
        price = 50000.0
        
        # Case 5A: Extreme Fear Restriction Gate (Fear & Greed Index < 20)
        # Sizing and status calculations are normal, but can_trade must return False
        allowed_fear, reason_fear = risk_manager.can_trade(balance=balance, open_trades=[], fear_greed_score=15)
        logger.info(f"-> Trade allowed in extreme fear (15)? {allowed_fear} | Reason: {reason_fear}")
        assert not allowed_fear
        assert "extreme market fear" in reason_fear.lower()
        
        # Case 5B: Normal Risk checks under regular market state (F&G >= 20)
        allowed_normal, reason_normal = risk_manager.can_trade(balance=balance, open_trades=[], fear_greed_score=50)
        logger.info(f"-> Trade allowed in normal market (50)? {allowed_normal} | Reason: {reason_normal}")
        assert allowed_normal
        
        # Case 5C: Position Sizing calculation metrics
        position = risk_manager.calculate_position(balance, price)
        logger.info(f"-> Sizing Cost: ${position.get('cost'):.2f} USDT | Qty: {position.get('quantity'):.6f}")
        logger.info(f"-> Stop Loss: ${position.get('stop_loss'):.2f} | Take Profit: ${position.get('take_profit'):.2f}")
        
        # USDT Sizing cost must be exactly 10% of total balance = $10.00
        assert abs(position.get("cost") - 10.0) < 1e-5
        # Stop loss must be exactly 3% below entry price = 48,500.00
        assert abs(position.get("stop_loss") - 48500.0) < 1e-5
        # Take profit must be exactly 6% above entry price = 53,000.00
        assert abs(position.get("take_profit") - 53000.0) < 1e-5
        
        logger.info("[Test 5] PASSED.")
    except Exception as e:
        logger.error(f"[Test 5] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # Test 6: Paper Order Executor Pipeline with Extreme Fear Integration
    # --------------------------------------------------------------------------
    try:
        logger.info("\n[Test 6] Testing Paper Order Executor Pipeline & Extreme Fear Gate integration...")
        
        # Set up a strong buy signal report
        signal_report = {
            "final_signal": 0.65,
            "action": "STRONG_BUY",
            "components": {
                "momentum": {"signal": 0.8},
                "sentiment": {"signal": 0.6},
                "arbitrage": {"signal": 0.5}
            }
        }
        current_price = 50000.0
        
        # Case 6A: Blocked execute_signal due to Extreme Fear Index (18 < 20)
        logger.info("-> Trying trade execution with F&G = 18...")
        trade_fear = executor.execute_signal("BTC/USDT", signal_report, current_price, fear_greed_score=18)
        logger.info(f"-> Returned trade object: {trade_fear}")
        assert trade_fear is None
        
        # Case 6B: Allowed trade execution under standard market environment (F&G = 45 >= 20)
        logger.info("-> Trying trade execution with F&G = 45...")
        trade_normal = executor.execute_signal("BTC/USDT", signal_report, current_price, fear_greed_score=45)
        logger.info(f"-> Returned trade object: {trade_normal}")
        assert trade_normal is not None
        assert trade_normal.get("pair") == "BTC/USDT"
        assert trade_normal.get("action") == "BUY"
        assert trade_normal.get("entry_price") == current_price
        assert abs(trade_normal.get("cost") - 10.0) < 1e-5
        
        logger.info("[Test 6] PASSED.")
    except Exception as e:
        logger.error(f"[Test 6] FAILED: {str(e)}", exc_info=True)
        success = False

    # --------------------------------------------------------------------------
    # COMPILING RESULTS
    # --------------------------------------------------------------------------
    logger.info("\n=== TESTS EXECUTION COMPLETE ===")
    if success:
        logger.info("ALL STRATEGY, COMBINER, RISK GATES, AND EXECUTOR CHECKS SUCCESSFULLY PASSED! [+]")
        sys.exit(0)
    else:
        logger.error("ONE OR MORE LOGIC VERIFICATION CHECKS FAILED! [X]")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()

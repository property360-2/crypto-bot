# ==============================================================================
# File: core/signal_combiner.py
# Purpose: Meta-Signal Combiner. Combines multiple sub-strategy weights into 
#          a unified final signal score to drive execution decisions.
# Fits into: Decision Core.
# ==============================================================================

import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("crypto_bot.core.signal_combiner")

def combine_signals(
    momentum_report: Dict[str, Any],
    sentiment_report: Dict[str, Any],
    arbitrage_report: Dict[str, Any],
    base_weights: Tuple[float, float, float] = (0.35, 0.35, 0.30)
) -> Dict[str, Any]:
    """
    Combines sub-signals using an adjustable weighted score matrix.
    
    NOTE: Option A Implementation:
          In Phase 1, since sentiment and arbitrage modules are inactive stubs,
          their weights are reassigned to momentum (making momentum weight 1.0) 
          so the final combined signal can achieve STRONG_BUY/STRONG_SELL targets.
          In Phase 2, when sentiment and arbitrage are live, the base weights 
          of (0.35, 0.35, 0.30) will be fully utilized.
          
    Accepts:
        momentum_report (dict): Report from momentum strategy.
        sentiment_report (dict): Report from sentiment strategy.
        arbitrage_report (dict): Report from arbitrage strategy.
        base_weights (tuple): Default relative weights (Momentum, Sentiment, Arbitrage).
    Returns:
        Dict[str, Any]: Consolidated signal report containing:
            - 'final_signal' (float): Weighted final signal (-1.0 to +1.0).
            - 'action' (str): Confluence decision ('STRONG_BUY', 'HOLD', 'STRONG_SELL').
            - 'components' (dict): Traceable sub-scores.
            - 'reasons' (list[str]): Explanation audit log.
    """
    logger.info("[-] Consolidating strategy sub-signals...")

    # Extract score values
    momentum_score = float(momentum_report.get("signal", 0.0))
    sentiment_score = float(sentiment_report.get("signal", 0.0))
    arbitrage_score = float(arbitrage_report.get("signal", 0.0))

    reasons = []
    
    # ==============================================================================
    # MULTI-STRATEGY WEIGHT ALLOCATION (PHASE 2 ACTIVE)
    # ==============================================================================
    w_momentum, w_sentiment, w_arbitrage = base_weights
    reasons.append(
        f"Running in Multi-Strategy Confluence Mode. "
        f"Weights: Momentum {w_momentum:.2f}, Sentiment {w_sentiment:.2f}, Arbitrage {w_arbitrage:.2f}"
    )

    # Compute final consolidated weighted score
    final_score = (
        (momentum_score * w_momentum) +
        (sentiment_score * w_sentiment) +
        (arbitrage_score * w_arbitrage)
    )
    
    # Clamp final signal score to -1.0 to +1.0 range
    final_score = max(-1.0, min(1.0, final_score))
    
    # ==============================================================================
    # CONFLUENCE DECISION ENGINE
    # ==============================================================================
    # STRONG_BUY: Score >= 0.60
    # STRONG_SELL: Score <= -0.60
    # HOLD: Anything else
    
    action = "HOLD"
    
    # Standard Multi-Strategy confluence threshold criteria for Phase 2
    if final_score >= 0.6:
        action = "STRONG_BUY"
        reasons.append(f"Combined signal {final_score:.2f} >= 0.6. Strong BUY confluence met.")
    elif final_score <= -0.6:
        action = "STRONG_SELL"
        reasons.append(f"Combined signal {final_score:.2f} <= -0.6. Strong SELL/EXIT confluence met.")
    else:
        action = "HOLD"
        reasons.append(f"Combined signal {final_score:.2f} in neutral zone. Action HOLD.")

    report = {
        "final_signal": round(final_score, 2),
        "action": action,
        "components": {
            "momentum": momentum_report,
            "sentiment": sentiment_report,
            "arbitrage": arbitrage_report,
            "weights": {
                "momentum": w_momentum,
                "sentiment": w_sentiment,
                "arbitrage": w_arbitrage
            }
        },
        "reasons": reasons
    }

    logger.info(f"[+] Consolidated Signal Computed: Action={action}, Combined Score={final_score:.2f}")
    return report

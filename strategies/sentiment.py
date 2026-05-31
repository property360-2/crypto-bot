# ==============================================================================
# File: strategies/sentiment.py
# Purpose: Active Sentiment Analysis Strategy Module (CryptoPanic news parser 
#          and Alternative.me Fear & Greed Index).
# Fits into: Strategy component namespace.
# ==============================================================================

import logging
from typing import Dict, Any, List
import httpx

import config

logger = logging.getLogger("crypto_bot.strategies.sentiment")

# ==============================================================================
# ALTERNATIVE.ME FEAR & GREED API POLLER
# ==============================================================================

def _fetch_fear_and_greed_score() -> int:
    """
    Fetches the latest Fear & Greed Index score from alternative.me.
    Returns 50 (neutral) on error or connection timeout.
    
    Accepts:
        None
    Returns:
        int: Fear & Greed score between 0 and 100.
    """
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        # NOTE: Using a short timeout to prevent slow cold starts or blocking the bot cycle
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            score_data = data.get("data", [])
            if score_data:
                score = int(score_data[0].get("value", 50))
                logger.info(f"[+] Loaded Fear & Greed Index: {score}")
                return score
        logger.warning(f"[!] F&G API returned status {response.status_code}. Defaulting to neutral (50).")
        return 50
    except Exception as e:
        logger.error(f"[X] Exception fetching Fear & Greed Index: {str(e)}. Defaulting to neutral (50).")
        return 50

# ==============================================================================
# CRYPTOPANIC NEWS SCRAPER
# ==============================================================================

def _fetch_cryptopanic_news() -> List[str]:
    """
    Fetches recent news headlines from CryptoPanic API.
    Returns empty list if token is missing or if connection fails.
    
    Accepts:
        None
    Returns:
        List[str]: List of news headline strings.
    """
    token = config.CRYPTOPANIC_TOKEN
    if not token or token == "your_cryptopanic_token_here":
        logger.info("[-] CryptoPanic token not configured. News parsing skipped.")
        return []

    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={token}&public=true"
    try:
        response = httpx.get(url, timeout=8.0)
        if response.status_code == 200:
            data = response.json()
            posts = data.get("results", [])
            headlines = [post.get("title", "") for post in posts if post.get("title")]
            logger.info(f"[+] Scraped {len(headlines)} headlines from CryptoPanic.")
            return headlines
        logger.warning(f"[!] CryptoPanic API returned status {response.status_code}.")
        return []
    except Exception as e:
        logger.error(f"[X] Exception scraping CryptoPanic headlines: {str(e)}")
        return []

# ==============================================================================
# SENTIMENT ANALYSIS ENGINES
# ==============================================================================

def _score_sentiment_locally(headlines: List[str]) -> float:
    """
    Local fast keyword-based sentiment scorer. Assesses positive vs negative connotes.
    Returns a score between -1.0 (bearish) and +1.0 (bullish).
    
    Accepts:
        headlines (list[str]): List of headline strings to evaluate.
    Returns:
        float: Calculated sentiment score.
    """
    if not headlines:
        return 0.0

    # Custom local dictionary
    positives = {"bullish", "long", "moon", "rise", "pump", "surge", "gain", "buy", "high", "growth", "breakout", "green", "support", "rally"}
    negatives = {"bearish", "short", "dump", "drop", "crash", "loss", "sell", "fear", "panic", "liquidate", "rejection", "red", "resistance", "ban"}

    total_score = 0.0
    for headline in headlines:
        words = set(headline.lower().replace("?", "").replace("!", "").split())
        pos_count = len(words.intersection(positives))
        neg_count = len(words.intersection(negatives))
        
        # Settle headline difference
        diff = pos_count - neg_count
        if diff > 0:
            total_score += 0.2
        elif diff < 0:
            total_score -= 0.2
            
    # Normalize score between -1.0 and +1.0
    avg_score = total_score / len(headlines)
    avg_score = max(-1.0, min(1.0, avg_score))
    return avg_score


def _score_sentiment_via_groq(headlines: List[str]) -> float:
    """
    Connects to the Groq API to perform professional sentiment analysis on news headlines.
    Falls back to local keyword scorer if Groq API key is missing or request fails.
    
    Accepts:
        headlines (list[str]): List of headline strings.
    Returns:
        float: Aggregated sentiment score between -1.0 (extremely bearish) and +1.0 (extremely bullish).
    """
    key = config.GROQ_API_KEY
    if not key or key == "your_groq_api_key_here":
        return _score_sentiment_locally(headlines)

    # Compile the headlines list into a prompt format
    prompt_headlines = "\n".join([f"- {h}" for h in headlines[:15]])  # Limit to top 15 to conserve tokens
    
    system_prompt = (
        "You are an elite quantitative sentiment analyst. Your task is to analyze "
        "the provided list of cryptocurrency news headlines and return a single aggregated "
        "sentiment score between -1.0 (extremely bearish) and +1.0 (extremely bullish). "
        "Your output must contain EXACTLY a float representation of the score and nothing else."
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-specdec",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Score these headlines:\n\n{prompt_headlines}"}
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }

    try:
        # Perform POST to Groq completions endpoint
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                text_result = choices[0].get("message", {}).get("content", "0.0").strip()
                try:
                    score = float(text_result)
                    score = max(-1.0, min(1.0, score))
                    logger.info(f"[+] Groq API Sentiment Score: {score}")
                    return score
                except ValueError:
                    logger.warning(f"[!] Groq returned invalid float format: {text_result}")
        logger.warning(f"[!] Groq API returned status {response.status_code}. Using local keyword fallback.")
        return _score_sentiment_locally(headlines)
    except Exception as e:
        logger.error(f"[X] Exception during Groq sentiment call: {str(e)}. Using local keyword fallback.")
        return _score_sentiment_locally(headlines)

# ==============================================================================
# MAIN STRATEGY ENTRY POINT
# ==============================================================================

def analyze() -> Dict[str, Any]:
    """
    Main executor. Scrapes news articles and Alternative.me indexes to 
    derive quantitative sentiment metrics.
    
    Accepts:
        None
    Returns:
        Dict[str, Any]: Consolidated sentiment report.
    """
    logger.info("[-] Starting sentiment analysis strategy loop...")
    reasons = []

    # 1. Fetch Alternative.me Fear & Greed Index
    fng_score = _fetch_fear_and_greed_score()
    
    # Map index to -1.0 to 1.0 score
    if fng_score > 70:
        fng_mapped = 0.5
        reasons.append(f"Fear & Greed Index is {fng_score} (Greed): Bullish bias (+0.5)")
    elif fng_score < 30:
        fng_mapped = -0.5
        reasons.append(f"Fear & Greed Index is {fng_score} (Fear): Bearish bias (-0.5)")
    else:
        fng_mapped = 0.0
        reasons.append(f"Fear & Greed Index is {fng_score} (Neutral): Neutral bias (0.0)")

    # 2. Fetch CryptoPanic news headlines
    headlines = _fetch_cryptopanic_news()
    
    # 3. Analyze news headlines
    if not headlines:
        news_score = 0.0
        reasons.append("No news headlines gathered. Defaulting news score to neutral (0.0)")
    else:
        # Determine analysis engine based on token presence
        if config.GROQ_API_KEY and config.GROQ_API_KEY != "your_groq_api_key_here":
            news_score = _score_sentiment_via_groq(headlines)
            reasons.append(f"Headlines scored via Groq API. Score: {news_score:+.2f}")
        else:
            news_score = _score_sentiment_locally(headlines)
            reasons.append(f"Headlines scored via Local Keyword Scorer. Score: {news_score:+.2f}")

    # 4. Consolidated weighted calculation
    # Final sentiment score = 50% Fear & Greed + 50% News score
    combined_score = (0.5 * fng_mapped) + (0.5 * news_score)
    combined_score = max(-1.0, min(1.0, combined_score))
    
    # Recommendations Action Tresholds
    action = "HOLD"
    if combined_score >= 0.3:
        action = "BUY"
        reasons.append(f"Sentiment confluence bullish ({combined_score:+.2f} >= 0.3): Action BUY")
    elif combined_score <= -0.3:
        action = "SELL"
        reasons.append(f"Sentiment confluence bearish ({combined_score:+.2f} <= -0.3): Action SELL")
    else:
        reasons.append(f"Sentiment score {combined_score:+.2f} neutral. Action HOLD")

    report = {
        "signal": round(combined_score, 2),
        "action": action,
        "indicators": {
            "fear_and_greed": fng_score,
            "fng_mapped": fng_mapped,
            "news_headlines_count": len(headlines),
            "news_score": round(news_score, 2),
        },
        "reasons": reasons
    }
    
    logger.info(f"[+] Sentiment analysis completed. Signal: {combined_score:+.2f}, Action: {action}")
    return report

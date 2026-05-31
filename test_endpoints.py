# ==============================================================================
# File: test_endpoints.py
# Purpose: Local integration testing script to verify running web API endpoints.
#          Queries the FastAPI server and prints parsed JSON outputs for health,
#          telemetry status, and live market cycles.
# Fits into: Quality Assurance and Live Validation checks.
# ==============================================================================

import json
import logging
from typing import Dict, Any
import httpx

# Configure basic logging for visual test console feedback
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] : %(message)s")
logger = logging.getLogger("crypto_bot.endpoint_tester")

def run_integration_tests() -> None:
    """
    Triggers HTTP GET requests sequentially to health, status, and run routes
    to verify dynamic server operations and logs outputs.
    
    Accepts:
        None
    Returns:
        None
    """
    base_url = "http://127.0.0.1:8000"
    
    logger.info("=== STARTING LIVE ENDPOINTS DYNAMIC INTEGRATION CHECKS ===")
    
    # 1. Verify health check endpoint '/'
    try:
        logger.info("[-] Triggering health check endpoint '/'...")
        response = httpx.get(f"{base_url}/", timeout=5.0)
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
        
        data = response.json()
        logger.info("[+] Health Check Response:")
        logger.info(json.dumps(data, indent=2))
        assert data.get("status") == "alive"
        logger.info("Health check verify: PASSED.")
    except Exception as e:
        logger.error(f"[X] Health check verify: FAILED - {str(e)}")
        return

    # 2. Verify status telemetry endpoint '/status'
    try:
        logger.info("\n[-] Triggering telemetry status check '/status'...")
        response = httpx.get(f"{base_url}/status", timeout=5.0)
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
        
        data = response.json()
        logger.info("[+] Status Telemetry Response:")
        logger.info(json.dumps(data, indent=2))
        assert "mode" in data
        assert "paper_balance_usdt" in data
        assert "latest_sentiment" in data
        logger.info("Status telemetry verify: PASSED.")
    except Exception as e:
        logger.error(f"[X] Status telemetry verify: FAILED - {str(e)}")
        return

    # 3. Trigger live market execution cycle '/run'
    try:
        logger.info("\n[-] Triggering live market cycle execution '/run' (Fetching live Binance spot/futures data)...")
        # NOTE: Using a longer timeout as CCXT queries standard Binance spot and futures APIs.
        response = httpx.get(f"{base_url}/run", timeout=20.0)
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
        
        data = response.json()
        logger.info("[+] Live Market Sweep Cycle Response:")
        logger.info(json.dumps(data, indent=2))
        assert data.get("status") == "completed"
        assert "scanned_pairs" in data
        assert "global_sentiment" in data
        logger.info("Live market sweep cycle verify: PASSED.")
    except Exception as e:
        logger.error(f"[X] Live market sweep cycle verify: FAILED - {str(e)}")
        return

    logger.info("\n=== ALL INTEGRATION ENDPOINT CHECKS SUCCESSFULLY COMPLETED! [+][+][+] ===")

if __name__ == "__main__":
    run_integration_tests()

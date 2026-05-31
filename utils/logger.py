# ==============================================================================
# File: utils/logger.py
# Purpose: Diagnostic logger configuration. Sets up standardized console output streams.
# Fits into: Support utilities package.
# ==============================================================================

import logging
import sys

# ==============================================================================
# DIAGNOSTIC LOGGER SETUP
# ==============================================================================

def setup_logging(level: int = logging.INFO) -> None:
    """
    Configures standard Python logging to write formatted logs to stdout.
    Stdout outputs are natively captured, stored, and indexed by Render hosting.
    
    Accepts:
        level (int): Log logging depth (default = logging.INFO).
    Returns:
        None
    """
    try:
        # Prevent double adding handlers if function is triggered multiple times
        root = logging.getLogger()
        if root.handlers:
            for handler in root.handlers:
                root.removeHandler(handler)

        # Clear active framework configurations
        logging.getLogger("uvicorn.access").handlers = []
        logging.getLogger("uvicorn.error").handlers = []

        # Create stdout handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        # Set up a structured clean prefix layout for readable audits
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] (%(name)s) : %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)

        # Apply to parent root logger
        root.addHandler(handler)
        root.setLevel(level)

        # Ensure active sub-logs respect global setting limits
        logging.getLogger("ccxt").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("firebase_admin").setLevel(logging.WARNING)

        logging.info("[+] Diagnostics logging initialized successfully.")
    except Exception as e:
        print(f"[X] Fatal setup_logging configuration failure: {str(e)}")

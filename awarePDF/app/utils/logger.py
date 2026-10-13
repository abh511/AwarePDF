# ============================================================
# app/utils/logger.py
# Centralized logging setup using Rich for pretty output
# Import this in every file: from app.utils.logger import get_logger
# ============================================================

import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()

# Configure root logger ONCE at import time — prevents duplicate handlers
# when multiple modules call get_logger().
_LOGGING_CONFIGURED = False


def _configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    # Remove any existing handlers to avoid duplicates on reloads
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(RichHandler(console=console, rich_tracebacks=True))
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger with Rich formatting.
    Usage: logger = get_logger(__name__)
    """
    _configure_logging()
    return logging.getLogger(name)

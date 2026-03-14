# ============================================================
# app/utils/logger.py
# Centralized logging setup using Rich for pretty output
# Import this in every file: from app.utils.logger import get_logger
# ============================================================

import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger with Rich formatting.
    Usage: logger = get_logger(__name__)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
    return logging.getLogger(name)

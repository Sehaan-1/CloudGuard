"""Structured logging configuration for CloudGuard."""

import logging
import sys
from typing import TextIO

try:
    from rich.console import Console
    from rich.logging import RichHandler

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def setup_logging(
    level: str = "INFO",
    stream: TextIO | None = None,
    use_rich: bool = True,
) -> logging.Logger:
    """Configure root logger for CloudGuard with Rich or standard StreamHandler."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("cloudguard")
    logger.setLevel(log_level)

    if logger.hasHandlers():
        logger.handlers.clear()

    if use_rich and HAS_RICH:
        console = Console(file=stream or sys.stderr)
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        )
        formatter = logging.Formatter("%(message)s")
    else:
        handler = logging.StreamHandler(stream or sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Retrieve a child logger under the cloudguard namespace."""
    if name.startswith("cloudguard"):
        return logging.getLogger(name)
    return logging.getLogger(f"cloudguard.{name}")

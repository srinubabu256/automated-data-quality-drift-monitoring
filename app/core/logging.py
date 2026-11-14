"""Centralized Structured Logging Configuration for YottaFlex Platform."""
import logging
import sys
from typing import Optional

from app.config import settings

DEFAULT_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)


def setup_logging(level: Optional[str] = None) -> None:
    """Configures structured console logging across all application loggers."""
    log_level_name = level or getattr(settings, "LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, log_level_name.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Retrieves a named logger instance configured with application formatting."""
    return logging.getLogger(name)

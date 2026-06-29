"""Application logging with a rotating file handler.

Writes to ``%APPDATA%/HaushaltsManager/logs/app.log`` with size-based
rotation so the log never grows unbounded. A short console handler is added
during development for convenience.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app_meta import APP_NAME, is_frozen, logs_dir

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logging once and return the app logger."""
    global _CONFIGURED
    logger = logging.getLogger(APP_NAME)
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = logs_dir() / "app.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # Console output is noise in a windowed (frozen) build; keep it for dev.
    if not is_frozen():
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

    logger.propagate = False
    _CONFIGURED = True
    logger.info("Logging initialised -> %s", log_file)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the app namespace."""
    base = logging.getLogger(APP_NAME)
    return base.getChild(name) if name else base

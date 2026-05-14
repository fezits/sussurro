from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_dir() -> Path:
    """Where to write logs. Next to the exe when frozen, project root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


_configured = False


def setup() -> logging.Logger:
    """Configure the root 'sussurro' logger to write to sussurro.log + stderr.
    Idempotent. Returns the logger so callers can use it directly.
    """
    global _configured
    logger = logging.getLogger("sussurro")
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = _log_dir() / "sussurro.log"
    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass

    try:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)
    except (OSError, ValueError):
        pass

    logger.info("=" * 60)
    logger.info(
        "Sussurro logger started · frozen=%s · log_path=%s",
        getattr(sys, "frozen", False),
        log_path,
    )
    _configured = True
    return logger


def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(f"sussurro.{name}")

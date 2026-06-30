"""Logging configuration built on the standard library ``logging`` package."""

from __future__ import annotations

import logging
import sys
from typing import Final

_LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once for the lifetime of the process."""
    global _configured
    if _configured:
        new_level = _coerce_level(level)
        if logging.getLogger().level != logging.DEBUG or new_level == logging.DEBUG:
            logging.getLogger().setLevel(new_level)
        return

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_coerce_level(level))

    # Quiet noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "git", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger, configuring root logging lazily."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


def _coerce_level(level: str) -> int:
    if level.isdigit():
        return int(level)
    return logging.getLevelName(level.upper())

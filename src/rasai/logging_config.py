"""Logging bootstrap."""

from __future__ import annotations

import logging

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def configure_logging(level: str) -> None:
    """Configure process logging using the standard library only."""

    logging.basicConfig(
        level=_LEVELS[level],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

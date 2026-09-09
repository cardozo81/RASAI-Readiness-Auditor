"""Logging bootstrap with mandatory secret redaction."""

from __future__ import annotations

import logging

from .secret_safety import redact_text

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


class SecretSafeFormatter(logging.Formatter):
    """Redact credential material after normal log/exception formatting."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def configure_logging(level: str) -> None:
    """Configure process logging with a secret-safe output formatter."""

    handler = logging.StreamHandler()
    handler.setFormatter(SecretSafeFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(
        level=_LEVELS[level],
        handlers=[handler],
        force=True,
    )

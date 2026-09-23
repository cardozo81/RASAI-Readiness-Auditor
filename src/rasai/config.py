"""Application configuration for the M0 bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

_DEFAULT_CONFIG_FILE = "rasai.toml"
_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Minimal application settings required by M0."""

    log_level: str = "INFO"


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load configuration from TOML and environment variables.

    The default file is ``rasai.toml`` in the current directory. A missing
    default file is valid. ``RASAI_CONFIG`` can select another file, and
    ``RASAI_LOG_LEVEL`` overrides the configured logging level.
    """

    explicit_path = path is not None or "RASAI_CONFIG" in os.environ
    config_path = Path(path or os.environ.get("RASAI_CONFIG", _DEFAULT_CONFIG_FILE))
    values: dict[str, object] = {}

    if config_path.is_file():
        with config_path.open("rb") as config_file:
            document = tomllib.load(config_file)
        section = document.get("rasai", {})
        if not isinstance(section, dict):
            raise ValueError("[rasai] must be a TOML table")
        values = section
    elif explicit_path:
        raise ValueError(f"configuration file not found: {config_path}")

    log_level = os.environ.get("RASAI_LOG_LEVEL", str(values.get("log_level", "INFO")))
    normalized_level = log_level.strip().upper()
    if normalized_level not in _VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ValueError(f"invalid log_level {log_level!r}; expected one of: {allowed}")

    return AppConfig(log_level=normalized_level)

"""Optional local GeoIP tool bootstrap before opening the RASAi console.

No download without persisted explicit consent. Never called by an AUD worker.
"""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path

from rasai.console_settings import resolve_config_path
from rasai.network_geoip_install import install_official_updater
from rasai.network_active_policy import validate_network_setting


def acquisition_authorized() -> bool:
    override = os.environ.get("RASAI_GEOIP_ACQUIRE_TOOLS")
    if override is None:
        path = resolve_config_path()
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 500_000:
            return False
        parser = ConfigParser(interpolation=None)
        try:
            parser.read(path, encoding="utf-8")
            override = parser.get("environment", "RASAI_GEOIP_ACQUIRE_TOOLS", fallback="false")
        except (OSError, ValueError):
            return False
    try:
        return validate_network_setting("RASAI_GEOIP_ACQUIRE_TOOLS", override) == "true"
    except (ValueError, TypeError):
        return False


def prepare() -> dict:
    """Non-blocking for product availability: status is advisory only."""
    if not acquisition_authorized():
        return {"state": "NOT_AUTHORIZED"}
    try:
        return install_official_updater(acquisition_authorized=True)
    except (OSError, ValueError):
        return {"state": "FAILED", "error": "MAXMIND_TOOL_BOOTSTRAP_FAILED"}


def main() -> None:
    print(json.dumps(prepare(), ensure_ascii=False))


if __name__ == "__main__":
    main()

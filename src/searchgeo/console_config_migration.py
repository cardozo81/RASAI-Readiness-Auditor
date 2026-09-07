"""Canonical interactive-console configuration path and legacy migration.

RASAi uses ``rasai-console.ini`` as the public configuration filename.  The
former ``searchgeo-console.ini`` name remains a one-time compatibility input:
when no explicit configuration override is present and only the legacy file
exists, it is atomically renamed to the canonical filename before the console
loads its settings.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, MutableMapping

CONSOLE_INI_ENV = "SEARCHGEO_CONSOLE_INI"
CANONICAL_CONSOLE_INI = "rasai-console.ini"
LEGACY_CONSOLE_INI = "searchgeo-console.ini"


def prepare_console_config(
    *,
    env: MutableMapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    """Resolve the public console config and migrate the legacy default safely.

    An explicit ``SEARCHGEO_CONSOLE_INI`` value is authoritative and is never
    rewritten.  Without an override, ``rasai-console.ini`` is canonical.  If
    it does not exist but ``searchgeo-console.ini`` does, the legacy file is
    atomically renamed in-place so existing non-secret settings are preserved.

    If both files exist, the canonical file wins and the legacy file is left
    untouched to avoid destroying potentially divergent user configuration.
    """
    environment = env if env is not None else os.environ
    base = (cwd if cwd is not None else Path.cwd()).resolve()

    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve()

    canonical = (base / CANONICAL_CONSOLE_INI).resolve()
    legacy = (base / LEGACY_CONSOLE_INI).resolve()

    if not canonical.exists() and legacy.exists():
        os.replace(legacy, canonical)

    environment[CONSOLE_INI_ENV] = str(canonical)
    return canonical


def canonical_console_config_path(
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    """Return the effective path without mutating the filesystem or environment."""
    environment = env if env is not None else os.environ
    base = (cwd if cwd is not None else Path.cwd()).resolve()
    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve()
    return (base / CANONICAL_CONSOLE_INI).resolve()

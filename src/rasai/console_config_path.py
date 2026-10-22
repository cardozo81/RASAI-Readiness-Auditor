"""Canonical interactive-console configuration path for RASAi."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, MutableMapping

CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
CANONICAL_CONSOLE_INI = "rasai-console.ini"


def prepare_console_config(*, env: MutableMapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    """Resolve the RASAi console configuration path."""
    environment = env if env is not None else os.environ
    base = (cwd if cwd is not None else Path.cwd()).resolve()
    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()
    path = Path(configured).expanduser() if configured else Path(CANONICAL_CONSOLE_INI)
    if not path.is_absolute():
        path = base / path
    # Keep the final INI component unresolved so load/save can reject an
    # existing or dangling symlink rather than silently following its target.
    resolved = path.parent.resolve() / path.name
    environment[CONSOLE_INI_ENV] = str(resolved)
    return resolved


def canonical_console_config_path(*, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    """Return the effective RASAi console configuration path without filesystem mutation."""
    environment = env if env is not None else os.environ
    base = (cwd if cwd is not None else Path.cwd()).resolve()
    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()
    path = Path(configured).expanduser() if configured else Path(CANONICAL_CONSOLE_INI)
    if not path.is_absolute():
        path = base / path
    # Resolving the leaf here bypasses the INI symlink guard.
    return path.parent.resolve() / path.name

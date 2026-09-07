"""Canonical local runtime paths for RASAi."""
from __future__ import annotations

from pathlib import Path

CANONICAL_RUNTIME_DIR = ".rasai"


def runtime_directory(root: str | Path) -> Path:
    """Return the canonical RASAi runtime metadata directory."""
    return Path(root) / CANONICAL_RUNTIME_DIR

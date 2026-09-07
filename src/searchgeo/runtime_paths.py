"""Canonical local runtime paths for RASAi with safe legacy migration.

The public product directory is ``.rasai``. ``.searchgeo`` is accepted only as
an on-disk legacy source during migration. Migration is conservative: missing
entries are moved into ``.rasai``; conflicting entries are left untouched so no
local evidence or control-plane data is overwritten.
"""
from __future__ import annotations

import os
from pathlib import Path

CANONICAL_RUNTIME_DIR = ".rasai"
LEGACY_RUNTIME_DIR = ".searchgeo"


def _merge_missing(source: Path, destination: Path) -> None:
    """Move source into destination without overwriting an existing entry."""
    if not source.exists():
        return
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        return
    if source.is_dir() and destination.is_dir():
        for child in tuple(source.iterdir()):
            _merge_missing(child, destination / child.name)
        try:
            source.rmdir()
        except OSError:
            pass


def migrate_runtime_directory(root: str | Path) -> Path:
    """Best-effort migration from ``.searchgeo`` to ``.rasai``.

    If both directories exist, ``.rasai`` is authoritative and only missing
    entries are moved from the legacy directory. Conflicting legacy entries are
    preserved rather than overwritten. If migration cannot complete (for
    example because Windows has a legacy SQLite file open), callers still get a
    usable legacy path when no canonical directory exists.
    """
    base = Path(root)
    canonical = base / CANONICAL_RUNTIME_DIR
    legacy = base / LEGACY_RUNTIME_DIR
    if not legacy.exists():
        return canonical
    try:
        _merge_missing(legacy, canonical)
    except OSError:
        pass
    if canonical.exists():
        return canonical
    return legacy


def runtime_directory(root: str | Path) -> Path:
    """Return the effective runtime metadata directory, migrating when needed."""
    return migrate_runtime_directory(root)

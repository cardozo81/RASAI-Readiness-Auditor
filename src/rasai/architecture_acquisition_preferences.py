"""Operator-selectable acquisition mode, independent of declared architecture.

Configuration is local to the launcher, small, and loaded on demand. No
Docker, browser, network or audit workspace is touched by preference reads.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATIC = "STATIC"
DYNAMIC = "DYNAMIC"
OPTIONS = frozenset((STATIC, DYNAMIC))
VERSION = 1


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def preference_path(root: Path | None = None) -> Path:
    base = (root or _root()).resolve()
    return base / ".rasai-runtime" / "architecture" / "acquisition.json"


def read_mode(root: Path | None = None) -> str:
    target = preference_path(root)
    try:
        if target.stat().st_size > 1024:
            return STATIC
        obj = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return STATIC
    if not isinstance(obj, dict) or set(obj) != {"version", "mode"}:
        return STATIC
    if type(obj["version"]) is not int or obj["version"] != VERSION:
        return STATIC
    return obj["mode"] if isinstance(obj["mode"], str) and obj["mode"] in OPTIONS else STATIC


def write_mode(mode: str, root: Path | None = None) -> None:
    if mode not in OPTIONS:
        raise ValueError("Unsupported discovery acquisition mode")
    target = preference_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps({"version": VERSION, "mode": mode}, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

"""Ephemeral metadata for one interactive-console process."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SessionMeta:
    config_path: Path | None = None
    dirty: bool = False
    volatile_secrets: set[str] = field(default_factory=set)


_META: dict[int, SessionMeta] = {}


def _meta(state: Any) -> SessionMeta:
    return _META.setdefault(id(state), SessionMeta())


def set_config_path(state: Any, path: Path) -> None:
    _meta(state).config_path = path


def get_config_path(state: Any) -> Path | None:
    return _meta(state).config_path


def mark_dirty(state: Any, dirty: bool = True) -> None:
    _meta(state).dirty = dirty


def is_dirty(state: Any) -> bool:
    return _meta(state).dirty


def mark_secret_volatile(state: Any, name: str = "*") -> None:
    _meta(state).volatile_secrets.add(name)


def clear_secret_volatile(state: Any, name: str) -> None:
    _meta(state).volatile_secrets.discard(name)


def has_volatile_secrets(state: Any) -> bool:
    return bool(_meta(state).volatile_secrets)


def clear_session_meta(state: Any) -> None:
    _META.pop(id(state), None)

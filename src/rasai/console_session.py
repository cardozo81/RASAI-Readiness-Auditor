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
    # Exact persistent baseline retained while this session overrides network consent.
    # The execution process sees the override; unrelated INI saves must not.
    volatile_network_consent: dict[str, str] | None = None


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


def get_volatile_network_consent(state: Any) -> dict[str, str] | None:
    value = _meta(state).volatile_network_consent
    return dict(value) if value is not None else None


def set_volatile_network_consent(state: Any, values: dict[str, str] | None) -> None:
    _meta(state).volatile_network_consent = dict(values) if values is not None else None


def clear_session_meta(state: Any) -> None:
    _META.pop(id(state), None)

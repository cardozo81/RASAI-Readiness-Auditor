"""Context-local non-secret execution environment overrides.

Selective AUD reprocessing must reproduce the original non-secret configuration while
resolving credentials from the current process environment. ContextVar keeps those
overrides isolated across concurrent workers and avoids mutating ``os.environ``.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import os
from typing import Any, Iterator, Mapping


_OVERRIDES: ContextVar[dict[str, str] | None] = ContextVar(
    "rasai_execution_environment_overrides",
    default=None,
)


def resolve_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return base environment plus context-local non-secret overrides."""
    values = dict(os.environ if env is None else env)
    overrides = _OVERRIDES.get()
    if overrides:
        values.update(overrides)
    return values


@contextmanager
def override_environment(values: Mapping[str, Any]) -> Iterator[None]:
    """Apply non-empty values only inside the current execution context."""
    current = dict(_OVERRIDES.get() or {})
    for name, value in values.items():
        key = str(name or "").strip()
        text = str(value or "").strip()
        if key and text:
            current[key] = text
    token = _OVERRIDES.set(current)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)

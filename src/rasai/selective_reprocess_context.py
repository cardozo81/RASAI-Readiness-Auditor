"""Per-execution context for selective recovery of optional AUD components.

The context is process-local and ContextVar-backed so concurrent workers do not share
pending-component state. Outside an AUD reprocessing run every component remains
eligible for its normal execution path.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(slots=True)
class SelectiveReprocessContext:
    audit_id: str
    pending_components: frozenset[str]
    workspace: Any | None = None
    extra_attempted: int = 0
    extra_successful: int = 0


_CURRENT: ContextVar[SelectiveReprocessContext | None] = ContextVar(
    "rasai_selective_optional_reprocess",
    default=None,
)


def current() -> SelectiveReprocessContext | None:
    return _CURRENT.get()


def active() -> bool:
    return _CURRENT.get() is not None


def should_execute(component: str) -> bool:
    """Normal execution is unchanged; RPR executes only components pending at start."""
    value = _CURRENT.get()
    if value is None:
        return True
    return component.strip().upper() in value.pending_components


def record_optional_evaluation(*, success: bool) -> None:
    value = _CURRENT.get()
    if value is None:
        return
    value.extra_attempted += 1
    if success:
        value.extra_successful += 1


@contextmanager
def scope(
    audit_id: str,
    pending_components: set[str] | frozenset[str],
    *,
    workspace: Any | None = None,
) -> Iterator[SelectiveReprocessContext]:
    value = SelectiveReprocessContext(
        audit_id=str(audit_id),
        pending_components=frozenset(str(item).strip().upper() for item in pending_components if str(item).strip()),
        workspace=workspace,
    )
    token = _CURRENT.set(value)
    try:
        yield value
    finally:
        _CURRENT.reset(token)

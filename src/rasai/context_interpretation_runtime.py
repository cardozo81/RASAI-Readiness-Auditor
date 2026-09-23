"""Composition hook for durable, non-canonical AUTO-context interpretation records."""
from __future__ import annotations

from typing import Any

_INSTALLED=False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:return
    from rasai import ai_exchange_log
    from rasai.context_interpretation_persistence import persist_context_interpretations

    current=ai_exchange_log.persist_ai_exchange_log
    if getattr(current,"_rasai_context_interpretation_persistence",False):
        _INSTALLED=True
        return

    def persist_with_context(*,audit_id: str,workspace: Any,recorder: Any) -> None:
        current(audit_id=audit_id,workspace=workspace,recorder=recorder)
        persist_context_interpretations(audit_id=audit_id,workspace=workspace,recorder=recorder)

    persist_with_context._rasai_context_interpretation_persistence=True
    persist_with_context._rasai_original=current
    ai_exchange_log.persist_ai_exchange_log=persist_with_context

    # improvement_exchange_capture imports the function by value. Patch the bound
    # reference when that module has already been imported by composition.
    try:
        from rasai import improvement_exchange_capture
        bound=getattr(improvement_exchange_capture,"persist_ai_exchange_log",None)
        if bound is current:
            improvement_exchange_capture.persist_ai_exchange_log=persist_with_context
    except ImportError:
        pass
    _INSTALLED=True


__all__=["install"]

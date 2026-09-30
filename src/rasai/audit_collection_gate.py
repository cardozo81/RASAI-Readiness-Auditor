"""One AUD/RPR collection-readiness contract at the AI execution boundary.

This module does not collect, call providers, mutate evidence, or infer missing
work from a best-effort diagnostic. Callers reconcile the original fulfillment
contract and complete the collection phase before evaluating this gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rasai.audit_fulfillment import DISABLED, NOT_APPLICABLE, SUCCESS, list_work_items
from rasai.operational_log import try_append_operational_event


# These components are computed *after* evidence collection, not dependencies
# of the collection itself. CORE_AUDIT closes after AI/final derivations.
POST_COLLECTION_COMPONENTS = frozenset({
    "CORE_AUDIT",
    "SEMANTIC_AI",
    "TECHNICAL_AI",
    "CONTENT_REMEDIATION_AI",
    "IMPROVEMENT_INTELLIGENCE",
    "COMPETITIVE_INTELLIGENCE",
})
SATISFIED_COLLECTION_STATES = frozenset({SUCCESS, NOT_APPLICABLE, DISABLED})


@dataclass(frozen=True, slots=True)
class CollectionReadiness:
    ready: bool
    required_count: int
    blockers: tuple[str, ...]


def evaluate_collection_readiness(workspace: Any, audit_id: str) -> CollectionReadiness:
    """Conservative, scope-aware AI gate shared by initial AUD and selective RPR.

    Required optional collectors remain in the denominator. Merely terminal
    errors (e.g. FAILED_RETRYABLE or blocked render) do *not* constitute
    collected evidence. Missing work items must be projected by the caller's
    contract reconciler before this function is invoked.
    """
    items = (
        item for item in list_work_items(workspace, audit_id)
        if bool(item.required)
        and str(item.component).upper() not in POST_COLLECTION_COMPONENTS
    )
    required_count = 0
    blockers: list[str] = []
    for item in items:
        required_count += 1
        component = str(item.component).upper()
        scope_key = str(item.scope_key)
        state = str(item.status).upper()
        if state not in SATISFIED_COLLECTION_STATES:
            blockers.append(f"{component}/{scope_key}:{state}")
    return CollectionReadiness(
        ready=not blockers,
        required_count=required_count,
        blockers=tuple(sorted(blockers)),
    )


def record_collection_gate(
    workspace: Any,
    audit_id: str,
    *,
    path: str,
    readiness: CollectionReadiness,
) -> None:
    """Log a safe causal decision without URL, evidence body or credentials."""
    try_append_operational_event(
        workspace,
        "AI_COLLECTION_GATE_READY" if readiness.ready else "AI_COLLECTION_GATE_DEFERRED",
        level="INFO" if readiness.ready else "WARNING",
        audit_id=audit_id,
        execution_path=str(path).upper(),
        required_collectors=readiness.required_count,
        blockers=readiness.blockers,
        gate_version="AUD_RPR_COLLECTION_GATE_V1",
    )


__all__ = [
    "CollectionReadiness",
    "POST_COLLECTION_COMPONENTS",
    "SATISFIED_COLLECTION_STATES",
    "evaluate_collection_readiness",
    "record_collection_gate",
]

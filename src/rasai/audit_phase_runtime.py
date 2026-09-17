"""Canonical phase registry for governed audit execution.

Optional integrations are composed by registration instead of by performing network
or AI work inside report finalizers.  The audit runner owns the causal order:

    core collection -> registered collection hooks -> evidence seal -> AI -> reporting

Hooks remain deliberately small and return state/provenance only.  Their existing
storage layers continue to persist the full raw datasets and observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from rasai.ai_governance import (
    EvidenceSnapshot,
    collection_state_is_terminal,
    latest_evidence_snapshot,
    seal_evidence,
)
from rasai.operational_log import try_append_operational_event


CollectionHook = Callable[..., Mapping[str, Any] | None]
AiHook = Callable[..., Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class _Hook:
    name: str
    callback: Callable[..., Mapping[str, Any] | None]
    order: int


_COLLECTION_HOOKS: dict[str, _Hook] = {}
_AI_HOOKS: dict[str, _Hook] = {}


def register_collection_hook(name: str, callback: CollectionHook, *, order: int = 100) -> None:
    key = str(name).strip().upper()
    if not key:
        raise ValueError("collection hook name must not be empty")
    _COLLECTION_HOOKS[key] = _Hook(key, callback, int(order))


def register_ai_hook(name: str, callback: AiHook, *, order: int = 100) -> None:
    key = str(name).strip().upper()
    if not key:
        raise ValueError("AI hook name must not be empty")
    _AI_HOOKS[key] = _Hook(key, callback, int(order))


def unregister_collection_hook(name: str) -> None:
    _COLLECTION_HOOKS.pop(str(name).strip().upper(), None)


def unregister_ai_hook(name: str) -> None:
    _AI_HOOKS.pop(str(name).strip().upper(), None)


def _normalized_state(result: Mapping[str, Any] | None) -> str:
    if result is None:
        return "SUCCESS"
    for key in ("collection_state", "status", "state", "service_state"):
        value = result.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().upper()
    return "SUCCESS"


def run_collection_phase(
    *,
    audit_id: str,
    workspace: Any,
    source_blocked: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Execute every registered collector before any governed AI consumer.

    Exceptions are converted to terminal ERROR states and logged.  Collectors own
    their normal fail-open/fail-closed business semantics; this coordinator only makes
    completion explicit so the AI phase cannot race a still-running collector.
    """

    states: dict[str, str] = {}
    details: dict[str, Any] = {}
    hooks = sorted(_COLLECTION_HOOKS.values(), key=lambda item: (item.order, item.name))
    try_append_operational_event(
        workspace,
        "EXTERNAL_COLLECTION_PHASE_STARTED",
        audit_id=audit_id,
        collectors=tuple(item.name for item in hooks),
        source_blocked=source_blocked,
    )
    for hook in hooks:
        try_append_operational_event(
            workspace,
            "COLLECTOR_STARTED",
            audit_id=audit_id,
            collector=hook.name,
        )
        try:
            raw = hook.callback(
                audit_id=audit_id,
                workspace=workspace,
                source_blocked=source_blocked,
            )
            result = dict(raw or {})
            state = _normalized_state(result)
            states[hook.name] = state
            details[hook.name] = result
            try_append_operational_event(
                workspace,
                "COLLECTOR_FINISHED",
                level="WARNING" if state in {"PARTIAL", "ERROR", "FAILED_RETRYABLE", "BLOCKED"} else "INFO",
                audit_id=audit_id,
                collector=hook.name,
                state=state,
            )
        except Exception as exc:
            state = "ERROR"
            states[hook.name] = state
            details[hook.name] = {
                "collection_state": state,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:512],
            }
            try_append_operational_event(
                workspace,
                "COLLECTOR_FAILURE",
                level="ERROR",
                audit_id=audit_id,
                collector=hook.name,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )
    nonterminal = tuple(
        name for name, state in states.items() if not collection_state_is_terminal(state)
    )
    try_append_operational_event(
        workspace,
        "EXTERNAL_COLLECTION_PHASE_FINISHED",
        level="ERROR" if nonterminal else "INFO",
        audit_id=audit_id,
        collector_states=states,
        nonterminal_collectors=nonterminal,
    )
    if nonterminal:
        raise RuntimeError(
            "collection phase returned non-terminal collector state(s): "
            + ", ".join(f"{name}={states[name]}" for name in nonterminal)
        )
    return states, details


def seal_collection_evidence(
    *,
    audit_id: str,
    workspace: Any,
    collection_states: Mapping[str, Any],
    collection_details: Mapping[str, Any] | None = None,
) -> EvidenceSnapshot:
    snapshot = seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        collection_states=collection_states,
        context={"collectors": dict(collection_details or {})},
    )
    try_append_operational_event(
        workspace,
        "EVIDENCE_SEALED",
        audit_id=audit_id,
        evidence_snapshot_id=snapshot.evidence_snapshot_id,
        evidence_version=snapshot.version_number,
        evidence_fingerprint=snapshot.fingerprint,
        evidence_count=len(snapshot.evidence_ids),
        collector_states=snapshot.collection_states,
    )
    return snapshot


def require_sealed_evidence(*, audit_id: str, workspace: Any) -> EvidenceSnapshot:
    snapshot = latest_evidence_snapshot(workspace, audit_id)
    if snapshot is None:
        raise RuntimeError("AI_CONTEXT_NOT_READY:EVIDENCE_NOT_SEALED")
    return snapshot


def run_registered_ai_phase(
    *,
    audit_id: str,
    workspace: Any,
    evidence_snapshot: EvidenceSnapshot,
) -> dict[str, Mapping[str, Any]]:
    """Run additive/post-derivation AI consumers before report materialization."""

    outcomes: dict[str, Mapping[str, Any]] = {}
    hooks = sorted(_AI_HOOKS.values(), key=lambda item: (item.order, item.name))
    for hook in hooks:
        try_append_operational_event(
            workspace,
            "AI_TASK_STARTED",
            audit_id=audit_id,
            purpose=hook.name,
            evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        )
        try:
            raw = hook.callback(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
            )
            result = dict(raw or {})
            outcomes[hook.name] = result
            try_append_operational_event(
                workspace,
                "AI_TASK_FINISHED",
                level="WARNING" if str(result.get("status") or "").upper() in {"PARTIAL", "ERROR", "FAILED"} else "INFO",
                audit_id=audit_id,
                purpose=hook.name,
                evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
                status=str(result.get("status") or "SUCCESS").upper(),
            )
        except Exception as exc:
            outcomes[hook.name] = {
                "status": "ERROR",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:512],
            }
            try_append_operational_event(
                workspace,
                "AI_TASK_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                purpose=hook.name,
                evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
                error_type=type(exc).__name__,
                error_message=str(exc)[:512],
            )
    return outcomes


def mark_ai_sealed(
    *,
    audit_id: str,
    workspace: Any,
    evidence_snapshot: EvidenceSnapshot,
    outcomes: Mapping[str, Any] | None = None,
) -> None:
    try_append_operational_event(
        workspace,
        "AI_SEALED",
        audit_id=audit_id,
        evidence_snapshot_id=evidence_snapshot.evidence_snapshot_id,
        evidence_fingerprint=evidence_snapshot.fingerprint,
        registered_ai_outcomes=dict(outcomes or {}),
    )


__all__ = [
    "register_collection_hook",
    "register_ai_hook",
    "unregister_collection_hook",
    "unregister_ai_hook",
    "run_collection_phase",
    "seal_collection_evidence",
    "require_sealed_evidence",
    "run_registered_ai_phase",
    "mark_ai_sealed",
]

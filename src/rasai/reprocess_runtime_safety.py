"""Concurrency-safe downstream recovery and generic RPR evaluation traceability.

Selective recovery must not mutate process-wide module functions per execution. This
module installs stable ContextVar-aware hooks for Content Remediation and records one
generic fulfillment evaluation for every downstream work-item processed by an RPR.
Provider/service-specific attempt tables remain authoritative for cost and diagnostics;
the generic attempt is the cross-component operational trace of the work-item itself.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from rasai.audit_fulfillment import recalculate


@dataclass(frozen=True, slots=True)
class _M20RecoveryContext:
    successful_snapshots: frozenset[str]


@dataclass(frozen=True, slots=True)
class _RprContext:
    audit_id: str
    reprocess_id: str | None = None


_M20_CONTEXT: ContextVar[_M20RecoveryContext | None] = ContextVar(
    "rasai_m20_recovery_context",
    default=None,
)
_RPR_CONTEXT: ContextVar[_RprContext | None] = ContextVar(
    "rasai_downstream_rpr_context",
    default=None,
)
_INSTALLED = False


def record_reprocess_evaluation(
    workspace: Any,
    *,
    item: Any,
    reprocess_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Append one finished generic work-item evaluation without changing effective state."""
    from rasai.audit_fulfillment import (
        _connect,
        _dump,
        _safe_mapping,
        _utc_now,
        _work_item_row,
        ensure_schema,
    )
    from rasai.domain import new_id

    ensure_schema(workspace)
    now = _utc_now()
    audit_id = str(item.audit_id)
    component = str(item.component)
    scope_key = str(item.scope_key)
    with _connect(workspace) as connection:
        row = _work_item_row(connection, audit_id, component, scope_key)
        number = int(row["attempt_count"]) + 1
        attempt_id = new_id("WKA")
        status = str(row["status"])
        connection.execute(
            """INSERT INTO audit_fulfillment_attempts(
                attempt_id,audit_id,work_item_id,reprocess_id,attempt_number,status,
                started_at,finished_at,error_class,error_code,error_message,result_ref,metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                attempt_id,
                audit_id,
                row["work_item_id"],
                reprocess_id,
                number,
                status,
                now,
                now,
                row["last_error_class"],
                row["last_error_code"],
                row["last_error_message"],
                row["effective_result_ref"] if status == "SUCCESS" else None,
                _dump(_safe_mapping({"kind": "REPROCESS_EVALUATION", **(metadata or {})})),
            ),
        )
        connection.execute(
            """UPDATE audit_fulfillment_work_items
               SET attempt_count=?,last_attempt_at=?,updated_at=? WHERE work_item_id=?""",
            (number, now, now, row["work_item_id"]),
        )
        connection.commit()
    recalculate(workspace, audit_id)
    return attempt_id


def _install_m20_factory_hook() -> None:
    from rasai import m20, reprocess_ai

    original = m20.build_content_remediation_router
    if bool(getattr(original, "_rasai_contextual_m20_recovery", False)):
        return

    def contextual_factory(provider: Any):
        router = original(provider)
        current = _M20_CONTEXT.get()
        if current is None:
            return router
        return reprocess_ai._SkipSuccessfulM20Router(
            router,
            current.successful_snapshots,
        )

    contextual_factory._rasai_contextual_m20_recovery = True
    contextual_factory._rasai_original = original
    m20.build_content_remediation_router = contextual_factory


def _install_m20_recovery() -> None:
    from rasai import m20, reprocess_ai

    current = reprocess_ai.recover_content_remediation
    if bool(getattr(current, "_rasai_contextual_m20_recovery", False)):
        return

    def recover_content_remediation_contextsafe(
        *,
        workspace: Any,
        audit_id: str,
        item: Any,
        provider: Any | None = None,
        force_all_contexts: bool = False,
    ) -> tuple[bool, Any, str]:
        active_provider = provider or reprocess_ai.build_reprocess_provider(
            workspace,
            audit_id,
            item,
        )
        successful = (
            frozenset()
            if force_all_contexts
            else reprocess_ai._successful_m20_snapshots(workspace, audit_id)
        )
        token = _M20_CONTEXT.set(_M20RecoveryContext(successful))
        try:
            result = m20.execute_m20(
                audit_id=audit_id,
                enabled=True,
                semantic_provider=active_provider,
                workspace=workspace,
            )
        finally:
            _M20_CONTEXT.reset(token)
        status = str(result.status)
        return (
            status in {"SUCCESS", "NO_SAFE_SUGGESTIONS", "NO_ELIGIBLE_FINDINGS"},
            active_provider,
            status,
        )

    recover_content_remediation_contextsafe._rasai_contextual_m20_recovery = True
    recover_content_remediation_contextsafe._rasai_original = current
    reprocess_ai.recover_content_remediation = recover_content_remediation_contextsafe


def _install_rpr_attempt_hooks() -> None:
    from rasai import audit_reprocess

    start = audit_reprocess.start_reprocess_run
    if not bool(getattr(start, "_rasai_rpr_attempt_context", False)):
        def contextual_start(workspace: Any, audit_id: str, *args: Any, **kwargs: Any) -> str:
            reprocess_id = start(workspace, audit_id, *args, **kwargs)
            current = _RPR_CONTEXT.get()
            if current is not None and current.audit_id == audit_id:
                _RPR_CONTEXT.set(_RprContext(audit_id, reprocess_id))
            return reprocess_id

        contextual_start._rasai_rpr_attempt_context = True
        contextual_start._rasai_original = start
        audit_reprocess.start_reprocess_run = contextual_start

    apply_result = audit_reprocess._apply_result
    if not bool(getattr(apply_result, "_rasai_rpr_attempt_context", False)):
        def traced_apply_result(workspace: Any, *, item: Any, **kwargs: Any) -> bool:
            result = apply_result(workspace, item=item, **kwargs)
            current = _RPR_CONTEXT.get()
            if (
                current is not None
                and current.reprocess_id
                and current.audit_id == str(item.audit_id)
            ):
                record_reprocess_evaluation(
                    workspace,
                    item=item,
                    reprocess_id=current.reprocess_id,
                    metadata={"component": str(item.component)},
                )
            return result

        traced_apply_result._rasai_rpr_attempt_context = True
        traced_apply_result._rasai_original = apply_result
        audit_reprocess._apply_result = traced_apply_result

    base = audit_reprocess.reprocess_audit
    if not bool(getattr(base, "_rasai_rpr_attempt_context", False)):
        def reprocess_with_attempt_context(
            audit_id: str,
            *,
            audits_root: Any = "audits",
            source: str = "CLI",
        ):
            token = _RPR_CONTEXT.set(_RprContext(audit_id, None))
            try:
                return base(audit_id, audits_root=audits_root, source=source)
            finally:
                _RPR_CONTEXT.reset(token)

        reprocess_with_attempt_context._rasai_rpr_attempt_context = True
        reprocess_with_attempt_context._rasai_original = base
        audit_reprocess.reprocess_audit = reprocess_with_attempt_context


def install() -> None:
    """Install stable per-execution recovery hooks once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m20_factory_hook()
    _install_m20_recovery()
    _install_rpr_attempt_hooks()
    _INSTALLED = True

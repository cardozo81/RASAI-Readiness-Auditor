"""Selective N-times recovery for one logical RASAi AUD.

The public invariant is simple: one AUD is one observation. Recovery creates RPR
execution versions but never a second observation. Successful work-items are reused,
failed retryable work-items are retried, and consolidated analytics accept the AUD
only after the original execution contract is fully satisfied and temporally valid.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from rasai.audit_fulfillment import (
    BLOCKED,
    COMPLETE,
    EXPIRED_FOR_COMPLETION,
    FAILED_PERMANENT,
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    PENDING,
    REPLAY_SAFE,
    SUCCESS,
    WAITING_FOR_DATA,
    WorkItem,
    finish_reprocess_run,
    initialize_contract,
    list_work_items,
    project_report_validity,
    read_summary,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace


@dataclass(frozen=True, slots=True)
class ReprocessResult:
    audit_id: str
    reprocess_id: str | None
    processing_status: str
    score_status: str
    report_status: str
    consolidation_eligible: bool
    attempted_items: int
    successful_items: int
    skipped_success_items: int
    remaining_items: int
    temporal_expired_items: int
    report_root: Path


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_expired(item: WorkItem) -> bool:
    if item.temporal_mode != LIVE_RECOLLECTION or item.status == SUCCESS:
        return False
    deadline = _parse_time(item.valid_until)
    return bool(deadline and _utc_now() > deadline)


def _backfill_contract(workspace: AuditWorkspace, audit_id: str) -> None:
    """Create the current contract from persisted evidence when it is absent.

    This is deterministic indexing of an existing AUD into the current fulfillment
    schema used by all executions.
    """
    initialize_contract(workspace, audit_id)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        audit = connection.execute("SELECT * FROM audits WHERE audit_id=?", (audit_id,)).fetchone()
        if audit is None:
            raise ValueError(f"audit_id not found in audit.db: {audit_id}")
        core_status = SUCCESS if str(audit["status"]) == "COMPLETED" else BLOCKED
        register_work_item(
            workspace,audit_id=audit_id,component="CORE_AUDIT",scope_key="AUDIT",required=True,
            temporal_mode=REPLAY_SAFE,status=core_status,retryable=False,
            configuration={"audit_status":str(audit["status"])},
        )
        if core_status == SUCCESS:
            set_work_item_status(
                workspace,audit_id=audit_id,component="CORE_AUDIT",scope_key="AUDIT",
                status=SUCCESS,result_ref=f"audit:{audit_id}",retryable=False,
            )

        if _table_exists(connection,"ai_audit_sessions"):
            session = connection.execute(
                "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,)
            ).fetchone()
            if session is not None and bool(session["enabled"]):
                strategy = str(session["strategy"] or session["initial_provider"] or "AUTO")
                snapshots = connection.execute(
                    """SELECT ps.snapshot_id FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                       WHERE p.audit_id=? ORDER BY ps.captured_at,ps.snapshot_id""", (audit_id,)
                ).fetchall()
                for raw in snapshots:
                    snapshot_id = str(raw["snapshot_id"])
                    attempts = connection.execute(
                        "SELECT * FROM ai_provider_attempts WHERE audit_id=? AND snapshot_id=? ORDER BY finished_at,rowid",
                        (audit_id,snapshot_id),
                    ).fetchall() if _table_exists(connection,"ai_provider_attempts") else ()
                    successful = any(str(row["status"]).upper() == "SUCCESS" for row in attempts)
                    assessments = 0
                    if _table_exists(connection,"semantic_assessments"):
                        assessments = int(connection.execute(
                            "SELECT count(*) FROM semantic_assessments WHERE snapshot_id=?", (snapshot_id,)
                        ).fetchone()[0])
                    status = SUCCESS if successful and assessments > 0 else FAILED_RETRYABLE
                    register_work_item(
                        workspace,audit_id=audit_id,component="SEMANTIC_AI",scope_key=snapshot_id,
                        required=True,temporal_mode=REPLAY_SAFE,status=status,retryable=True,
                        configuration={"provider":strategy},
                    )
                    if status == SUCCESS:
                        set_work_item_status(
                            workspace,audit_id=audit_id,component="SEMANTIC_AI",scope_key=snapshot_id,
                            status=SUCCESS,result_ref=f"semantic:{snapshot_id}",
                        )

        # Runtime-owned optional domains are indexed through one shared routine so
        # initial execution and explicit recovery use exactly the same semantics.
    finally:
        connection.close()

    from rasai.audit_fulfillment_runtime import _sync_persisted_components
    _sync_persisted_components(audit_id=audit_id,workspace=workspace)
    recalculate(workspace,audit_id)


def _latest_pending(workspace: AuditWorkspace, audit_id: str) -> tuple[WorkItem, ...]:
    return tuple(item for item in list_work_items(workspace,audit_id,pending_only=True) if item.required)


def _apply_result(
    workspace: AuditWorkspace,
    *,
    item: WorkItem,
    success: bool,
    error_code: str,
    result_ref: str,
) -> bool:
    if success:
        set_work_item_status(
            workspace,audit_id=item.audit_id,component=item.component,scope_key=item.scope_key,
            status=SUCCESS,result_ref=result_ref,retryable=True,
        )
        return True
    set_work_item_status(
        workspace,audit_id=item.audit_id,component=item.component,scope_key=item.scope_key,
        status=FAILED_RETRYABLE,error_class="RECOVERY",error_code=error_code,
        error_message=f"selective reprocessing did not satisfy {item.component}/{item.scope_key}",retryable=True,
    )
    return False


def reprocess_audit(
    audit_id: str,
    *,
    audits_root: str | Path = "audits",
    source: str = "CLI",
) -> ReprocessResult:
    """Retry only unresolved required work-items for ``audit_id``.

    The function is intentionally repeatable. Calling it after COMPLETE is a no-op
    that returns the current final state; it never re-executes successful services.
    """
    workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
    _backfill_contract(workspace,audit_id)
    before = list_work_items(workspace,audit_id)
    skipped_success = sum(item.required and item.status == SUCCESS for item in before)
    pending = _latest_pending(workspace,audit_id)
    summary = recalculate(workspace,audit_id)
    if summary.processing_status == COMPLETE or not pending:
        project_report_validity(audit_id=audit_id,workspace=workspace)
        return ReprocessResult(
            audit_id=audit_id,reprocess_id=None,processing_status=summary.processing_status,
            score_status=summary.score_status,report_status=summary.report_status,
            consolidation_eligible=summary.consolidation_eligible,attempted_items=0,successful_items=0,
            skipped_success_items=skipped_success,remaining_items=summary.pending_items+summary.blocked_items,
            temporal_expired_items=summary.expired_items,report_root=workspace.root / "report-catalog",
        )

    reprocess_id = start_reprocess_run(workspace,audit_id,source=source)
    attempted = 0
    successes = 0
    semantic_changed = False
    technical_changed = False
    shared_provider: Any | None = None
    dependency_m20_invalidated = False

    try_append_operational_event(
        workspace,"AUDIT_REPROCESS_STARTED",audit_id=audit_id,reprocess_id=reprocess_id,
        pending_items=len(pending),skipped_success_items=skipped_success,
    )

    # Replay-safe semantic items run first because they can change downstream
    # findings, scoring and content-remediation inputs.
    for item in pending:
        if item.component != "SEMANTIC_AI":
            continue
        if _is_expired(item):
            continue
        attempted += 1
        try:
            from rasai.reprocess_ai import recover_semantic_item
            success, shared_provider = recover_semantic_item(
                workspace=workspace,audit_id=audit_id,item=item,reprocess_id=reprocess_id,provider=shared_provider,
            )
        except Exception as exc:
            success = False
            try_append_operational_event(
                workspace,"AUDIT_REPROCESS_ITEM_FAILURE",level="WARNING",audit_id=audit_id,
                reprocess_id=reprocess_id,component=item.component,scope_key=item.scope_key,
                error_type=type(exc).__name__,error_message=str(exc)[:512],
            )
        if _apply_result(
            workspace,item=item,success=success,error_code="SEMANTIC_AI_RETRY_INCOMPLETE",
            result_ref=f"semantic:{item.scope_key}:effective",
        ):
            successes += 1
            semantic_changed = True

    if semantic_changed:
        from rasai.reprocess_ai import invalidate_content_remediation_dependency
        dependency_m20_invalidated = invalidate_content_remediation_dependency(workspace,audit_id)
        recalculate(workspace,audit_id)

    # Technical AI can change its bounded score contribution and therefore must be
    # resolved before the derived scoring pass.
    for item in _latest_pending(workspace,audit_id):
        if item.component != "TECHNICAL_AI":
            continue
        attempted += 1
        try:
            from rasai.reprocess_ai import recover_technical_ai
            success, shared_provider = recover_technical_ai(
                workspace=workspace,audit_id=audit_id,item=item,reprocess_id=reprocess_id,provider=shared_provider,
            )
        except Exception as exc:
            success = False
            try_append_operational_event(
                workspace,"AUDIT_REPROCESS_ITEM_FAILURE",level="WARNING",audit_id=audit_id,
                reprocess_id=reprocess_id,component=item.component,scope_key=item.scope_key,
                error_type=type(exc).__name__,error_message=str(exc)[:512],
            )
        if _apply_result(
            workspace,item=item,success=success,error_code="TECHNICAL_AI_RETRY_INCOMPLETE",
            result_ref="technical-ai:effective",
        ):
            successes += 1
            technical_changed = True

    if semantic_changed or technical_changed:
        from rasai.reprocess_ai import recompute_derived_after_ai
        recompute_derived_after_ai(
            workspace=workspace,audit_id=audit_id,reprocess_id=reprocess_id,semantic_changed=semantic_changed,
        )

    # If semantic recovery altered findings, M20 is re-evaluated against the new
    # effective finding set even when its previous version had succeeded.
    for item in _latest_pending(workspace,audit_id):
        if item.component != "CONTENT_REMEDIATION_AI":
            continue
        attempted += 1
        try:
            from rasai.reprocess_ai import recover_content_remediation
            success, shared_provider, m20_status = recover_content_remediation(
                workspace=workspace,audit_id=audit_id,item=item,provider=shared_provider,
                force_all_contexts=dependency_m20_invalidated,
            )
        except Exception as exc:
            success = False
            m20_status = type(exc).__name__
            try_append_operational_event(
                workspace,"AUDIT_REPROCESS_ITEM_FAILURE",level="WARNING",audit_id=audit_id,
                reprocess_id=reprocess_id,component=item.component,scope_key=item.scope_key,
                error_type=type(exc).__name__,error_message=str(exc)[:512],
            )
        if success and str(m20_status) == "NO_ELIGIBLE_FINDINGS":
            set_work_item_status(
                workspace,audit_id=audit_id,component=item.component,scope_key=item.scope_key,
                status=NOT_APPLICABLE,result_ref="content-remediation:not-applicable",retryable=False,
            )
            successes += 1
        elif _apply_result(
            workspace,item=item,success=success,error_code="CONTENT_REMEDIATION_RETRY_INCOMPLETE",
            result_ref=f"content-remediation:{m20_status}",
        ):
            successes += 1

    # Live collectors are retried only inside the same bounded observation window.
    for item in _latest_pending(workspace,audit_id):
        if item.component not in {"WEB_PERFORMANCE","SYNTHETIC_APDEX","EXPERIENCE_APDEX"}:
            continue
        if _is_expired(item):
            try_append_operational_event(
                workspace,"AUDIT_REPROCESS_ITEM_EXPIRED",level="WARNING",audit_id=audit_id,
                reprocess_id=reprocess_id,component=item.component,scope_key=item.scope_key,
                valid_until=item.valid_until,
            )
            continue
        attempted += 1
        try:
            if item.component == "WEB_PERFORMANCE":
                from rasai.reprocess_measurements import recover_web_performance
                success = recover_web_performance(workspace=workspace,audit_id=audit_id,item=item)
                ref = "web-performance:effective"
            elif item.component == "SYNTHETIC_APDEX":
                from rasai.reprocess_measurements import recover_synthetic_apdex
                success = recover_synthetic_apdex(workspace=workspace,audit_id=audit_id,item=item)
                ref = "synthetic-apdex:effective"
            else:
                from rasai.reprocess_measurements import recover_experience_apdex
                success = recover_experience_apdex(workspace=workspace,audit_id=audit_id,item=item)
                ref = "experience-apdex:effective"
        except Exception as exc:
            success = False
            ref = f"{item.component.casefold()}:incomplete"
            try_append_operational_event(
                workspace,"AUDIT_REPROCESS_ITEM_FAILURE",level="WARNING",audit_id=audit_id,
                reprocess_id=reprocess_id,component=item.component,scope_key=item.scope_key,
                error_type=type(exc).__name__,error_message=str(exc)[:512],
            )
        if _apply_result(
            workspace,item=item,success=success,error_code=f"{item.component}_RETRY_INCOMPLETE",result_ref=ref,
        ):
            successes += 1

    # Late functional finalizers run first; report-catalog is then regenerated from
    # the current effective persisted state. The retired <AUD>/report/ family is not
    # recreated during reprocessing.
    try:
        from rasai.report_completion import (
            finalize_audit_report_site,
            materialize_catalog_report_projection,
        )
        finalize_audit_report_site(audit_id=audit_id,workspace=workspace)
        materialize_catalog_report_projection(audit_id=audit_id,workspace=workspace)
    except Exception as exc:
        try_append_operational_event(
            workspace,"AUDIT_REPROCESS_REPORT_FAILURE",level="ERROR",audit_id=audit_id,reprocess_id=reprocess_id,
            error_type=type(exc).__name__,error_message=str(exc)[:512],
        )

    summary = project_report_validity(audit_id=audit_id,workspace=workspace)
    run_status = SUCCESS if summary.processing_status == COMPLETE else FAILED_RETRYABLE
    summary = finish_reprocess_run(
        workspace,reprocess_id,status=run_status,attempted_items=attempted,successful_items=successes,
        note=("all configured requirements satisfied" if summary.processing_status == COMPLETE else "one or more configured requirements remain unresolved"),
    )
    summary = project_report_validity(audit_id=audit_id,workspace=workspace)
    try_append_operational_event(
        workspace,"AUDIT_REPROCESS_COMPLETED",audit_id=audit_id,reprocess_id=reprocess_id,
        processing_status=summary.processing_status,score_status=summary.score_status,
        report_status=summary.report_status,consolidation_eligible=summary.consolidation_eligible,
        attempted_items=attempted,successful_items=successes,remaining_items=summary.pending_items+summary.blocked_items,
        temporal_expired_items=summary.expired_items,
    )
    return ReprocessResult(
        audit_id=audit_id,reprocess_id=reprocess_id,processing_status=summary.processing_status,
        score_status=summary.score_status,report_status=summary.report_status,
        consolidation_eligible=summary.consolidation_eligible,attempted_items=attempted,
        successful_items=successes,skipped_success_items=skipped_success,
        remaining_items=summary.pending_items+summary.blocked_items,
        temporal_expired_items=summary.expired_items,report_root=workspace.root / "report-catalog",
    )

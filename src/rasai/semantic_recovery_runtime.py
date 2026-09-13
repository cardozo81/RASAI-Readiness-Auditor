"""Semantic prerequisite gating and replay-safe recovery for selective AUD reprocessing.

Semantic AI is allowed only when the persisted snapshot has sufficient extracted content
and the deterministic HTML/rendering prerequisites are successful. A reprocess may
re-run extraction from the original persisted RAW/rendered artifact, but it never
re-fetches the audited page to manufacture a new semantic source inside the old AUD.
If the original source artifact is absent, the semantic requirement is blocked and a new
AUD is required. This preserves temporal/source integrity while still recovering pure
extraction failures without another provider call or another website request.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rasai.audit_fulfillment import (
    BLOCKED,
    FAILED_RETRYABLE,
    WAITING_FOR_DATA,
    archive_rows,
    list_work_items,
    set_work_item_status,
)
from rasai.domain import RuleResult
from rasai.persistence import AuditPersistence, AuditWorkspace

_INSTALLED = False


def _semantic_ready(workspace: AuditWorkspace, snapshot_id: str) -> bool:
    with AuditPersistence(workspace) as persistence:
        snapshot = persistence.snapshots.get(snapshot_id)
    if snapshot is None or not snapshot.main_content_ref:
        return False
    path = workspace.root / snapshot.main_content_ref
    if not path.is_file():
        return False
    try:
        return bool(path.read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        return False


def _source_artifact(workspace: AuditWorkspace, snapshot: Any) -> Path | None:
    for reference in (snapshot.rendered_artifact_ref, snapshot.raw_artifact_ref):
        if not reference:
            continue
        path = workspace.root / str(reference)
        if path.is_file():
            return path
    return None


def _archive_snapshot_before_replay(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    snapshot_id: str,
    reprocess_id: str,
) -> None:
    import sqlite3

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM page_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is not None:
        archive_rows(
            workspace,
            audit_id=audit_id,
            reprocess_id=reprocess_id,
            component="SEMANTIC_PREREQUISITE",
            entity_type="page_snapshot_extraction_state",
            entity_id="snapshot_id",
            id_field="snapshot_id",
            rows=(dict(row),),
        )


def _replay_original_extraction(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    snapshot_id: str,
    reprocess_id: str,
) -> str:
    """Retry M4 only from the original persisted source; never perform live recollection."""
    from rasai.m3 import M3ExecutionResult
    from rasai.m4 import execute_m4

    with AuditPersistence(workspace) as persistence:
        snapshot = persistence.snapshots.get(snapshot_id)
        if snapshot is None:
            return "SNAPSHOT_NOT_FOUND"
        if _source_artifact(workspace, snapshot) is None:
            return "ORIGINAL_SOURCE_ARTIFACT_UNAVAILABLE"
        page_id = snapshot.page_id
        device = snapshot.device

    _archive_snapshot_before_replay(
        workspace,
        audit_id=audit_id,
        snapshot_id=snapshot_id,
        reprocess_id=reprocess_id,
    )
    with AuditPersistence(workspace) as persistence:
        result = execute_m4(
            M3ExecutionResult(snapshot_ids={page_id: {device: snapshot_id}}, failures=()),
            persistence,
            workspace,
        )
    if result.failures:
        return str(result.failures[0].error_kind or "EXTRACTION_REPLAY_FAILED")
    if not _semantic_ready(workspace, snapshot_id):
        return "MAIN_CONTENT_STILL_UNAVAILABLE"
    return "SUCCESS"


def _rule_result(persistence: Any, execution_ids: Any, rule_id: str, *, snapshot_id: str | None = None) -> RuleResult | None:
    result: RuleResult | None = None
    for execution_id in tuple(execution_ids or ()):
        execution = persistence.rule_executions.get(execution_id)
        if execution is None or execution.rule_id != rule_id:
            continue
        if snapshot_id is not None and execution.snapshot_id not in {None, snapshot_id}:
            continue
        result = execution.result
    return result


def _dependency_reason(
    *,
    persistence: Any,
    m5_result: Any,
    m6_result: Any,
    snapshot_id: str,
) -> str | None:
    html = _rule_result(persistence, getattr(m5_result, "rule_execution_ids", ()), "BR-GEO-009")
    rendered = _rule_result(
        persistence,
        getattr(m6_result, "rule_execution_ids", ()),
        "BR-GEO-020",
        snapshot_id=snapshot_id,
    )
    if html is not RuleResult.PASS:
        return f"TECHNICAL_PREREQUISITE_BR_GEO_009_{getattr(html, 'value', 'MISSING')}"
    if rendered is not RuleResult.PASS:
        return f"TECHNICAL_PREREQUISITE_BR_GEO_020_{getattr(rendered, 'value', 'MISSING')}"
    return None


class _DependencyGatedProvider:
    def __init__(self, base: Any, reasons: dict[str, str], *, workspace: Any, audit_id: str) -> None:
        self.base = base
        self.reasons = reasons
        self.workspace = workspace
        self.audit_id = audit_id
        self.name = getattr(base, "name", "NONE")

    def analyze(self, semantic_input: Any):
        from rasai.semantic import ProviderCallResult, ProviderState

        snapshot_id = str(getattr(semantic_input, "snapshot_id", ""))
        reason = self.reasons.get(snapshot_id)
        if reason:
            try:
                set_work_item_status(
                    self.workspace,
                    audit_id=self.audit_id,
                    component="SEMANTIC_AI",
                    scope_key=snapshot_id,
                    status=WAITING_FOR_DATA,
                    error_class="PREREQUISITE",
                    error_code=reason,
                    error_message=f"AI_WAITING_FOR_DATA:{reason}",
                    retryable=True,
                )
            except (KeyError, OSError):
                pass
            return ProviderCallResult(
                ProviderState.UNAVAILABLE,
                reason=f"AI_WAITING_FOR_DATA:{reason}",
            )
        return self.base.analyze(semantic_input)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)


def _dependency_gate(original):
    if bool(getattr(original, "_rasai_semantic_dependency_gate", False)):
        return original

    def execute_m7_with_dependency_gate(*args: Any, **kwargs: Any):
        persistence = kwargs.get("persistence")
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        m3_result = kwargs.get("m3_result")
        m5_result = kwargs.get("m5_result")
        m6_result = kwargs.get("m6_result")
        provider = kwargs.get("provider")
        if not audit_id or persistence is None or workspace is None or m3_result is None or provider is None:
            return original(*args, **kwargs)
        reasons: dict[str, str] = {}
        for per_device in getattr(m3_result, "snapshot_ids", {}).values():
            for snapshot_id in per_device.values():
                reason = _dependency_reason(
                    persistence=persistence,
                    m5_result=m5_result,
                    m6_result=m6_result,
                    snapshot_id=str(snapshot_id),
                )
                if reason:
                    reasons[str(snapshot_id)] = reason
        if not reasons:
            return original(*args, **kwargs)
        patched = dict(kwargs)
        patched["provider"] = _DependencyGatedProvider(
            provider,
            reasons,
            workspace=workspace,
            audit_id=audit_id,
        )
        return original(*args, **patched)

    execute_m7_with_dependency_gate._rasai_semantic_dependency_gate = True
    execute_m7_with_dependency_gate._rasai_original = original
    return execute_m7_with_dependency_gate


def _wrap_recover_semantic_item(original):
    if bool(getattr(original, "_rasai_semantic_prerequisite_recovery", False)):
        return original

    def recover_semantic_with_prerequisite(*args: Any, **kwargs: Any):
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        item = kwargs.get("item")
        reprocess_id = str(kwargs.get("reprocess_id") or "")
        provider = kwargs.get("provider")
        if workspace is None or item is None or not audit_id or not reprocess_id:
            return original(*args, **kwargs)
        snapshot_id = str(getattr(item, "scope_key", ""))
        if snapshot_id in {"", "AUDIT"}:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="SEMANTIC_AI",
                scope_key=snapshot_id or "AUDIT",
                status=BLOCKED,
                error_class="PREREQUISITE",
                error_code="SEMANTIC_CONTEXT_NOT_RECOVERABLE",
                error_message="semantic context cannot be reconstructed for this AUD",
                retryable=False,
            )
            return False, provider
        if not _semantic_ready(workspace, snapshot_id):
            replay = _replay_original_extraction(
                workspace=workspace,
                audit_id=audit_id,
                snapshot_id=snapshot_id,
                reprocess_id=reprocess_id,
            )
            if replay == "ORIGINAL_SOURCE_ARTIFACT_UNAVAILABLE":
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="SEMANTIC_AI",
                    scope_key=snapshot_id,
                    status=BLOCKED,
                    error_class="PREREQUISITE",
                    error_code=replay,
                    error_message="original HTML/DOM source was not preserved; create a new AUD instead of live-refetching semantic source",
                    retryable=False,
                )
                return False, provider
            if replay != "SUCCESS":
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="SEMANTIC_AI",
                    scope_key=snapshot_id,
                    status=FAILED_RETRYABLE,
                    error_class="EXTRACTION",
                    error_code=replay,
                    error_message="replay-safe extraction did not produce sufficient semantic input",
                    retryable=True,
                )
                return False, provider
        return original(*args, **kwargs)

    recover_semantic_with_prerequisite._rasai_semantic_prerequisite_recovery = True
    recover_semantic_with_prerequisite._rasai_original = original
    return recover_semantic_with_prerequisite


def _wrap_apply_result(original):
    if bool(getattr(original, "_rasai_preserve_prerequisite_state", False)):
        return original

    def apply_result_preserving_prerequisite(workspace: AuditWorkspace, *, item: Any, success: bool, error_code: str, result_ref: str) -> bool:
        if not success and str(getattr(item, "component", "")) == "SEMANTIC_AI":
            current = next(
                (
                    candidate
                    for candidate in list_work_items(workspace, item.audit_id)
                    if candidate.component == item.component and candidate.scope_key == item.scope_key
                ),
                None,
            )
            if current is not None and current.status in {WAITING_FOR_DATA, BLOCKED, FAILED_RETRYABLE}:
                return False
        return original(
            workspace,
            item=item,
            success=success,
            error_code=error_code,
            result_ref=result_ref,
        )

    apply_result_preserving_prerequisite._rasai_preserve_prerequisite_state = True
    apply_result_preserving_prerequisite._rasai_original = original
    return apply_result_preserving_prerequisite


def install() -> None:
    """Install semantic dependency gates and replay-safe prerequisite recovery once."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_reprocess, audit_runner, m7, reprocess_ai

    # Main audit path: the fulfillment wrapper is already installed, so this outer
    # layer prevents its provider from reaching a paid endpoint when BR-GEO-009/020
    # do not prove a usable semantic source.
    audit_runner.execute_m7 = _dependency_gate(audit_runner.execute_m7)

    # Explicit AUD recovery imports m7.execute_m7 directly, so gate that path too.
    m7.execute_m7 = _dependency_gate(m7.execute_m7)
    reprocess_ai.recover_semantic_item = _wrap_recover_semantic_item(reprocess_ai.recover_semantic_item)
    audit_reprocess._apply_result = _wrap_apply_result(audit_reprocess._apply_result)

    _INSTALLED = True

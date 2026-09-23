"""Focused invariants for the governed evidence -> AI -> derivation pipeline."""
from __future__ import annotations

import inspect
import sqlite3
from types import SimpleNamespace

from rasai import ai_governance, ai_selective_invalidation, audit_runner
from rasai.audit_phase_runtime import require_sealed_evidence


def _workspace(tmp_path, audit_id: str = "AUD-GOV"):
    root = tmp_path / audit_id
    root.mkdir()
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE evidence(
                evidence_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                page_id TEXT,
                snapshot_id TEXT,
                observed_value TEXT
            );
            """
        )
        connection.execute("INSERT INTO audits(audit_id) VALUES(?)", (audit_id,))
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root, database=database), audit_id


def test_collection_terminal_states_fail_closed_for_unknown_values() -> None:
    for value in (
        "SUCCESS",
        "PARTIAL",
        "ERROR",
        "FAILED_RETRYABLE",
        "FAILED_PERMANENT",
        "BLOCKED",
        "SKIPPED",
        "DISABLED",
        "NOT_CONFIGURED",
        "NOT_APPLICABLE",
        "NO_DATA",
        "REQUESTED_NOT_EXECUTED",
        "SKIPPED_SOURCE_BLOCKER",
    ):
        assert ai_governance.collection_state_is_terminal(value) is True

    for value in ("PENDING", "RUNNING", "PROCESSING", "WAITING_FOR_DATA", "UNKNOWN", "NEW_STATE"):
        assert ai_governance.collection_state_is_terminal(value) is False


def test_dependency_gate_distinguishes_terminal_from_required_success() -> None:
    ready, missing, degraded = ai_governance.dependency_gate(
        expected=("GSC", "CLARITY"),
        present={"GSC": "PARTIAL", "CLARITY": "ERROR"},
    )
    assert ready is True
    assert missing == ()
    assert degraded == ()

    ready, missing, degraded = ai_governance.dependency_gate(
        expected=("GSC", "CLARITY"),
        present={"GSC": "PARTIAL", "CLARITY": "SUCCESS"},
        success_required=("GSC",),
    )
    assert ready is False
    assert missing == ()
    assert degraded == ("GSC",)

    ready, missing, degraded = ai_governance.dependency_gate(
        expected=("GSC", "CLARITY"),
        present={"GSC": "SUCCESS", "CLARITY": "RUNNING"},
    )
    assert ready is False
    assert missing == ("CLARITY",)
    assert degraded == ()


def test_evidence_snapshot_is_reused_until_fingerprint_changes(tmp_path) -> None:
    workspace, audit_id = _workspace(tmp_path)

    first = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"GSC": "SUCCESS"},
        context={"deterministic": {"version": 1}},
    )
    same = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"GSC": "SUCCESS"},
        context={"deterministic": {"version": 1}},
    )
    changed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"GSC": "PARTIAL"},
        context={"deterministic": {"version": 1}},
    )

    assert first.evidence_snapshot_id == same.evidence_snapshot_id
    assert first.version_number == same.version_number == 1
    assert changed.evidence_snapshot_id != first.evidence_snapshot_id
    assert changed.version_number == 2
    assert changed.fingerprint != first.fingerprint


def test_ai_context_requires_an_existing_evidence_seal(tmp_path) -> None:
    workspace, audit_id = _workspace(tmp_path)

    try:
        require_sealed_evidence(audit_id=audit_id, workspace=workspace)
    except RuntimeError as exc:
        assert str(exc) == "AI_CONTEXT_NOT_READY:EVIDENCE_NOT_SEALED"
    else:
        raise AssertionError("AI context was released without EVIDENCE_SEALED")

    sealed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"CORE": "SUCCESS"},
    )
    assert require_sealed_evidence(audit_id=audit_id, workspace=workspace) == sealed


def test_selective_invalidation_stales_only_changed_dependency_slice(tmp_path) -> None:
    workspace, audit_id = _workspace(tmp_path)
    first = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"GSC": "SUCCESS", "CLARITY": "SUCCESS"},
        context={"revision": 1},
    )

    gsc_task = ai_governance.register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="TEST_GSC",
        scope_type="AUDIT",
        scope_key="GSC",
        evidence_snapshot_id=first.evidence_snapshot_id,
        requirements=("summary",),
        status=ai_governance.TASK_COMPLETE,
    )
    clarity_task = ai_governance.register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="TEST_CLARITY",
        scope_type="AUDIT",
        scope_key="CLARITY",
        evidence_snapshot_id=first.evidence_snapshot_id,
        requirements=("summary",),
        status=ai_governance.TASK_COMPLETE,
    )
    ai_selective_invalidation.register_task_dependency(
        workspace=workspace,
        ai_task_id=gsc_task,
        dependency_kind="AUDIT_EVIDENCE",
        collection_keys=("GSC",),
    )
    ai_selective_invalidation.register_task_dependency(
        workspace=workspace,
        ai_task_id=clarity_task,
        dependency_kind="AUDIT_EVIDENCE",
        collection_keys=("CLARITY",),
    )

    prior_tasks = ai_selective_invalidation._task_state_before_seal(
        workspace,
        audit_id,
        first.evidence_snapshot_id,
    )
    second = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"GSC": "ERROR", "CLARITY": "SUCCESS"},
        context={"revision": 2},
    )
    ai_selective_invalidation._reconcile_staleness(
        workspace=workspace,
        audit_id=audit_id,
        prior_snapshot=first,
        new_snapshot=second,
        prior_tasks=prior_tasks,
    )

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = {
            row["ai_task_id"]: row
            for row in connection.execute(
                "SELECT ai_task_id,status,stale_reason FROM ai_tasks WHERE audit_id=?",
                (audit_id,),
            )
        }
        validated = connection.execute(
            "SELECT validated_snapshot_id FROM ai_task_dependency_specs WHERE ai_task_id=?",
            (clarity_task,),
        ).fetchone()
    finally:
        connection.close()

    assert rows[gsc_task]["status"] == ai_governance.TASK_STALE
    assert str(rows[gsc_task]["stale_reason"]).startswith("DEPENDENCY_CHANGED:")
    assert rows[clarity_task]["status"] == ai_governance.TASK_COMPLETE
    assert rows[clarity_task]["stale_reason"] is None
    assert validated is not None and validated[0] == second.evidence_snapshot_id


def test_audit_runner_keeps_ai_before_final_business_derivations() -> None:
    target = audit_runner.run_audit
    seen: set[int] = set()
    while callable(getattr(target, "_rasai_original", None)) and id(target) not in seen:
        seen.add(id(target))
        target = target._rasai_original
    source = inspect.getsource(target)

    assert source.index("run_collection_phase(") < source.index("seal_collection_evidence(")
    assert source.index("seal_collection_evidence(") < source.index("execute_m7(")
    assert source.index("execute_m20(") < source.index("mark_ai_sealed(")
    assert source.index("run_registered_ai_phase(") < source.index("mark_ai_sealed(")
    assert source.index("mark_ai_sealed(") < source.index("execute_pre_scoring_rules(")
    assert source.index("execute_pre_scoring_rules(") < source.index("execute_m9(")
    assert source.index("execute_m9(") < source.index("execute_m10(")
    assert source.index("execute_m10(") < source.index("evaluate_recommendations(")

def test_content_ai_gate_recovers_semantic_completion_from_durable_task(tmp_path) -> None:
    from rasai import audit_progress_runtime

    workspace, audit_id = _workspace(tmp_path, "AUD-DURABLE-SEMANTIC")
    sealed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"CORE": "SUCCESS"},
    )
    ai_governance.register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="SEMANTIC_M7",
        scope_type="SNAPSHOT",
        scope_key="SNP-1",
        evidence_snapshot_id=sealed.evidence_snapshot_id,
        requirements=("BR-GEO-028",),
        status=ai_governance.TASK_COMPLETE,
    )
    audit_progress_runtime._flags(workspace).discard("SEMANTIC_ANALYSIS")

    audit_progress_runtime._assert_ready(
        audit_id=audit_id,
        workspace=workspace,
        operation="CONTENT_REMEDIATION_AI",
        required_flags=("SEMANTIC_ANALYSIS",),
    )

    assert "SEMANTIC_ANALYSIS" in audit_progress_runtime._flags(workspace)


def test_audit_failure_reconciles_requested_improvement_before_failed_event() -> None:
    target = audit_runner.run_audit
    seen: set[int] = set()
    while callable(getattr(target, "_rasai_original", None)) and id(target) not in seen:
        seen.add(id(target))
        target = target._rasai_original
    source = inspect.getsource(target)

    assert "_reconcile_requested_improvement(workspace, audit_id)" in source
    assert source.index("_reconcile_requested_improvement(workspace, audit_id)") < source.index('"AUDIT_FAILED"')

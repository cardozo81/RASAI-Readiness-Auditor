"""Focused regressions for #164: semantic evidence must stay snapshot-bound."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
import sqlite3
from types import SimpleNamespace

from rasai import (
    ai_governance,
    ai_selective_invalidation,
    governed_analysis_runtime,
    m7,
    semantic_partial_runtime,
)
from rasai.domain import Audit, DeviceContext, EvidenceType, Page, PageSnapshot, RuleResult
from rasai.evidence import EvidenceManager
from rasai.m4 import M4ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.post_smoke_alignment import _backfill_semantic_task
from rasai.semantic import SemanticEvidenceInput, SemanticInput
from rasai.semantic_persistence import SemanticAssessment, SemanticPersistence


AUDIT_ID = "AUD-ISSUE-164"
PAGE_ID = "PGE-ISSUE-164"
SNAPSHOT_ID = "SNP-ISSUE-164"


def _workspace(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    audit = Audit(audit_id=AUDIT_ID, project_name="issue 164")
    page = Page(
        page_id=PAGE_ID,
        audit_id=AUDIT_ID,
        normalized_url="https://example.test/",
        discovered_url="https://example.test/",
    )
    main = workspace.artifacts / "extraction" / "main_content.txt"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("Conteúdo semântico inicial.", encoding="utf-8")
    snapshot = PageSnapshot(
        snapshot_id=SNAPSHOT_ID,
        page_id=PAGE_ID,
        device=DeviceContext.MOBILE,
        requested_url=page.normalized_url,
        final_url=page.normalized_url,
        captured_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        http_status=200,
        content_type="text/html",
        title="Exemplo",
        main_content_ref=main.relative_to(workspace.root).as_posix(),
    )
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.pages.add(page)
        persistence.snapshots.add(snapshot)
        rendered = EvidenceManager(persistence).record(
            audit_id=AUDIT_ID,
            page_id=PAGE_ID,
            snapshot_id=SNAPSHOT_ID,
            device=DeviceContext.MOBILE,
            evidence_type=EvidenceType.MAIN_CONTENT,
            source="RENDERED_DOM",
            observed_value={"excerpt": "Conteúdo semântico inicial."},
            artifact_reference=snapshot.main_content_ref,
        )
    return workspace, audit, page, snapshot, main, rendered.evidence_id


def _context_rows(workspace):
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT * FROM evidence
               WHERE audit_id=? AND snapshot_id=? AND source='semantic-input-builder'
               ORDER BY captured_at,evidence_id""",
            (AUDIT_ID, SNAPSHOT_ID),
        ).fetchall()
    finally:
        connection.close()


def test_semantic_context_is_materialized_before_seal_and_reused_by_m7(tmp_path) -> None:
    workspace, audit, page, snapshot, _, rendered_id = _workspace(tmp_path)

    first = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    second = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )

    assert first == second
    assert len(first) == 1
    assert len(_context_rows(workspace)) == 1

    sealed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        collection_states={"CORE": "SUCCESS"},
    )
    assert first[0] in sealed.evidence_ids

    with AuditPersistence(workspace) as persistence:
        semantic_input, context_id = m7._build_semantic_input(
            audit,
            page.normalized_url,
            snapshot,
            M4ExecutionResult(
                evidence_ids={SNAPSHOT_ID: (rendered_id,)},
                failures=(),
            ),
            persistence,
            workspace,
            EvidenceManager(persistence),
        )

    assert context_id == first[0]
    assert context_id in semantic_input.allowed_evidence_ids
    assert set(semantic_input.allowed_evidence_ids).issubset(set(sealed.evidence_ids))
    assert len(_context_rows(workspace)) == 1


def test_semantic_context_refreshes_when_persisted_source_changes(tmp_path) -> None:
    workspace, _, _, _, main, _ = _workspace(tmp_path)

    first = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )
    main.write_text("Conteúdo semântico corrigido em RPR.", encoding="utf-8")
    second = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )

    assert first != second
    rows = _context_rows(workspace)
    assert len(rows) == 2

    sealed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        collection_states={"CORE": "SUCCESS"},
    )
    assert second[0] in sealed.evidence_ids


def test_provider_boundary_rejects_input_evidence_outside_declared_snapshot() -> None:
    semantic_input = SemanticInput(
        snapshot_id=SNAPSHOT_ID,
        page_url="https://example.test/",
        title="Exemplo",
        main_content="Conteúdo",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EV-IN",
                evidence_type="TEXT_EXCERPT",
                source="semantic-input-builder",
                observed_value={"text": "Conteúdo"},
            ),
        ),
    )
    sealed = SimpleNamespace(evidence_ids=("EV-SEALED",))

    assert semantic_partial_runtime._semantic_input_snapshot_gap(
        semantic_input,
        sealed,
    ) == ("EV-IN",)

    source = inspect.getsource(semantic_partial_runtime._install_m7_continuation)
    assert source.index("if _semantic_input_snapshot_gap") < source.index(
        "task_id = register_task"
    )
    assert source.index("if _semantic_input_snapshot_gap") < source.index(
        "call = original_safe"
    )


def test_snapshot_dependency_tracks_semantic_context_but_ignores_downstream_evidence(
    tmp_path,
) -> None:
    workspace, _, _, snapshot, main, _ = _workspace(tmp_path)
    context_id = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )[0]
    sealed = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        collection_states={"CORE": "SUCCESS"},
    )

    first = ai_selective_invalidation.dependency_fingerprint(
        workspace=workspace,
        audit_id=AUDIT_ID,
        evidence_snapshot_id=sealed.evidence_snapshot_id,
        dependency_kind="SNAPSHOT_EVIDENCE",
        scope_key=SNAPSHOT_ID,
    )

    with AuditPersistence(workspace) as persistence:
        EvidenceManager(persistence).record(
            audit_id=AUDIT_ID,
            page_id=PAGE_ID,
            snapshot_id=SNAPSHOT_ID,
            device=DeviceContext.MOBILE,
            evidence_type=EvidenceType.COMPARISON,
            source="pre-scoring:BR-GEO-054",
            observed_value={"reproducible": True},
        )

    unchanged = ai_selective_invalidation.dependency_fingerprint(
        workspace=workspace,
        audit_id=AUDIT_ID,
        evidence_snapshot_id=sealed.evidence_snapshot_id,
        dependency_kind="SNAPSHOT_EVIDENCE",
        scope_key=SNAPSHOT_ID,
    )
    assert unchanged == first

    main.write_text("Conteúdo semântico alterado.", encoding="utf-8")
    refreshed_id = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )[0]
    assert refreshed_id != context_id

    changed = ai_selective_invalidation.dependency_fingerprint(
        workspace=workspace,
        audit_id=AUDIT_ID,
        evidence_snapshot_id=sealed.evidence_snapshot_id,
        dependency_kind="SNAPSHOT_EVIDENCE",
        scope_key=SNAPSHOT_ID,
    )
    assert changed != first


def test_no_ai_deterministic_baseline_is_not_backfilled_as_ai_task(tmp_path) -> None:
    workspace, _, _, _, _, _ = _workspace(tmp_path)
    context_id = m7.materialize_semantic_context_evidence(
        audit_id=AUDIT_ID,
        workspace=workspace,
    )[0]
    ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        collection_states={"CORE": "SUCCESS"},
    )

    with SemanticPersistence(workspace) as semantic:
        semantic.add_assessment(
            SemanticAssessment(
                assessment_id="SMA-BASELINE",
                snapshot_id=SNAPSHOT_ID,
                assessment_type="BR-GEO-028",
                result=RuleResult.PASS,
                confidence=0.9,
                evidence_ids=(context_id,),
                prompt_id="deterministic-semantic-baseline",
                prompt_version="1",
                provider="DETERMINISTIC_BASELINE",
                model=None,
                configuration_version="SEMANTIC-BASELINE-001",
                reasoning_summary="baseline",
            )
        )

    _backfill_semantic_task(workspace, AUDIT_ID)

    connection = sqlite3.connect(workspace.database)
    try:
        tasks = connection.execute(
            "SELECT COUNT(*) FROM ai_tasks WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
        rounds = connection.execute(
            """SELECT COUNT(*)
               FROM ai_request_rounds r
               JOIN ai_tasks t ON t.ai_task_id=r.ai_task_id
               WHERE t.audit_id=?""",
            (AUDIT_ID,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert tasks == 0
    assert rounds == 0


def test_semantic_context_hook_runs_before_fulfillment_sync() -> None:
    source = inspect.getsource(governed_analysis_runtime._install_phase_hooks)
    assert source.index('"SEMANTIC_CONTEXT"') < source.index('"FULFILLMENT_SYNC"')

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from rasai.audit_fulfillment import WAITING_FOR_DATA, initialize_contract, list_work_items, register_work_item, start_reprocess_run
from rasai.domain import Audit, DeviceContext, Page, PageSnapshot, RuleExecution, RuleResult, new_id, utc_now
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.semantic import ProviderCallResult, ProviderState
from rasai.semantic_recovery_runtime import (
    _DependencyGatedProvider,
    _dependency_reason,
    _replay_original_extraction,
)

_HTML = """<!doctype html><html><head><title>Recovered</title></head><body><main><h1>Recovered</h1><p>Persisted semantic source with enough content for replay-safe extraction.</p></main></body></html>"""


def _workspace(root: Path, *, with_source: bool = True):
    audit = Audit(audit_id="AUD-SEMANTIC-RECOVERY", project_name="semantic recovery")
    page = Page(
        page_id="PGE-RECOVERY",
        audit_id=audit.audit_id,
        normalized_url="https://example.test/recovery",
        discovered_url="https://example.test/recovery",
    )
    rendered_ref = None
    workspace = AuditWorkspace.create(root, audit.audit_id)
    if with_source:
        rendered = workspace.artifacts / "rendered" / "recovery.html"
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_text(_HTML, encoding="utf-8")
        rendered_ref = rendered.relative_to(workspace.root).as_posix()
    snapshot = PageSnapshot(
        snapshot_id="SNP-RECOVERY",
        page_id=page.page_id,
        device=DeviceContext.MOBILE,
        requested_url=page.normalized_url,
        final_url=page.normalized_url,
        captured_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        http_status=200,
        content_type="text/html",
        rendered_artifact_ref=rendered_ref,
    )
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.pages.add(page)
        persistence.snapshots.add(snapshot)
    initialize_contract(workspace, audit.audit_id, {"semantic_ai_requested": True})
    register_work_item(
        workspace,
        audit_id=audit.audit_id,
        component="SEMANTIC_AI",
        scope_key=snapshot.snapshot_id,
        required=True,
        status=WAITING_FOR_DATA,
        configuration={"provider": "FAKE"},
    )
    return workspace, audit, page, snapshot


def test_replay_safe_extraction_recovers_semantic_input_without_network() -> None:
    with TemporaryDirectory() as directory:
        workspace, audit, _, snapshot = _workspace(Path(directory), with_source=True)
        reprocess_id = start_reprocess_run(workspace, audit.audit_id)

        result = _replay_original_extraction(
            workspace=workspace,
            audit_id=audit.audit_id,
            snapshot_id=snapshot.snapshot_id,
            reprocess_id=reprocess_id,
        )

        assert result == "SUCCESS"
        with AuditPersistence(workspace) as persistence:
            recovered = persistence.snapshots.get(snapshot.snapshot_id)
            assert recovered is not None
            assert recovered.main_content_ref
            assert (workspace.root / recovered.main_content_ref).is_file()
            assert "Persisted semantic source" in (workspace.root / recovered.main_content_ref).read_text(encoding="utf-8")
        connection = sqlite3.connect(workspace.database)
        try:
            archived = connection.execute(
                "SELECT count(*) FROM audit_reprocess_derived_archive WHERE audit_id=? AND reprocess_id=? AND entity_type='page_snapshot_extraction_state'",
                (audit.audit_id, reprocess_id),
            ).fetchone()[0]
        finally:
            connection.close()
        assert archived == 1


def test_missing_original_source_is_not_live_refetched_inside_old_aud() -> None:
    with TemporaryDirectory() as directory:
        workspace, audit, _, snapshot = _workspace(Path(directory), with_source=False)
        reprocess_id = start_reprocess_run(workspace, audit.audit_id)

        result = _replay_original_extraction(
            workspace=workspace,
            audit_id=audit.audit_id,
            snapshot_id=snapshot.snapshot_id,
            reprocess_id=reprocess_id,
        )

        assert result == "ORIGINAL_SOURCE_ARTIFACT_UNAVAILABLE"


def test_dependency_gate_never_calls_provider_when_semantic_prerequisite_is_missing() -> None:
    class Provider:
        name = "FAKE"

        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, semantic_input):
            self.calls += 1
            return ProviderCallResult(ProviderState.AVAILABLE)

    with TemporaryDirectory() as directory:
        workspace, audit, _, snapshot = _workspace(Path(directory), with_source=True)
        base = Provider()
        gated = _DependencyGatedProvider(
            base,
            {snapshot.snapshot_id: "TECHNICAL_PREREQUISITE_BR_GEO_020_UNKNOWN"},
            workspace=workspace,
            audit_id=audit.audit_id,
        )

        result = gated.analyze(SimpleNamespace(snapshot_id=snapshot.snapshot_id))

        assert result.state is ProviderState.UNAVAILABLE
        assert str(result.reason).startswith("AI_WAITING_FOR_DATA:")
        assert base.calls == 0
        item = next(item for item in list_work_items(workspace, audit.audit_id) if item.component == "SEMANTIC_AI")
        assert item.status == WAITING_FOR_DATA
        assert item.attempt_count == 0


def test_dependency_resolution_is_scoped_to_page_and_snapshot() -> None:
    with TemporaryDirectory() as directory:
        workspace, audit, page_a, snapshot_a = _workspace(Path(directory), with_source=True)
        page_b = Page(
            page_id="PGE-OTHER",
            audit_id=audit.audit_id,
            normalized_url="https://example.test/other",
            discovered_url="https://example.test/other",
        )
        snapshot_b = PageSnapshot(
            snapshot_id="SNP-OTHER",
            page_id=page_b.page_id,
            device=DeviceContext.MOBILE,
            requested_url=page_b.normalized_url,
            final_url=page_b.normalized_url,
            captured_at=datetime(2026, 9, 13, 12, 1, tzinfo=timezone.utc),
            http_status=200,
            content_type="text/html",
        )
        executions: list[str] = []
        with AuditPersistence(workspace) as persistence:
            persistence.pages.add(page_b)
            persistence.snapshots.add(snapshot_b)
            for rule_id, page_id, snapshot_id, result in (
                ("BR-GEO-009", page_a.page_id, None, RuleResult.PASS),
                ("BR-GEO-020", page_a.page_id, snapshot_a.snapshot_id, RuleResult.PASS),
                ("BR-GEO-009", page_b.page_id, None, RuleResult.FAIL),
                ("BR-GEO-020", page_b.page_id, snapshot_b.snapshot_id, RuleResult.UNKNOWN),
            ):
                execution = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id=rule_id,
                    rule_version="test",
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.MOBILE if snapshot_id else None,
                    result=result,
                    observed_value={"test": True},
                    expected_condition="test",
                    evidence_ids=(),
                    executed_at=utc_now(),
                )
                persistence.rule_executions.add(execution)
                executions.append(execution.rule_execution_id)

            m5 = SimpleNamespace(rule_execution_ids=(executions[0], executions[2]))
            m6 = SimpleNamespace(rule_execution_ids=(executions[1], executions[3]))
            assert _dependency_reason(
                persistence=persistence,
                m5_result=m5,
                m6_result=m6,
                page_id=page_a.page_id,
                snapshot_id=snapshot_a.snapshot_id,
            ) is None
            reason = _dependency_reason(
                persistence=persistence,
                m5_result=m5,
                m6_result=m6,
                page_id=page_b.page_id,
                snapshot_id=snapshot_b.snapshot_id,
            )
            assert reason == "TECHNICAL_PREREQUISITE_BR_GEO_009_FAIL"

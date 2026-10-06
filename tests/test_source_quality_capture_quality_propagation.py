from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.audit_fulfillment import FAILED_RETRYABLE, WAITING_FOR_DATA
from rasai.content_extractability import execute_content_extractability
from rasai.core_reprocessing import (
    CONTENT_EXTRACTION,
    RENDER_CAPTURE,
    _recover_render,
    synchronize_core_work_items,
)
from rasai.domain import (
    Audit,
    DeviceContext,
    Page,
    PageSnapshot,
    RuleExecution,
    RuleResult,
    new_id,
)
from rasai.evidence import EvidenceManager
from rasai.javascript_spa import JavascriptSpaAnalyzer
from rasai.m3 import M3ExecutionResult
from rasai.m6 import _PriorState, execute_m6_snapshot_scope
from rasai.m7 import execute_m7
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import BrowserRenderResult
from rasai.rules import DependencyResolver
from rasai.scoring import ScoreConfidence, ScoringEngine, _metadata
from rasai.semantic import ProviderCallResult, ProviderState
from rasai.spa_persistence import SnapshotArchitectureWriter
from tests.test_core_reprocessing import _by_component, _workspace as core_workspace
from tests.test_m7_semantic_provider import _fixture as m7_fixture


_NOW = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)


def _quality(state: str) -> dict[str, object]:
    return {
        "render_succeeded": True,
        "capture_quality": {
            "contract_version": "RENDER-CAPTURE-QUALITY-001",
            "state": state,
            "reason": f"fixture-{state.casefold()}",
        },
    }


def _set_snapshot_quality(workspace: AuditWorkspace, snapshot_id: str, state: str) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                "UPDATE page_snapshots SET browser_metadata=? WHERE snapshot_id=?",
                (json.dumps(_quality(state), sort_keys=True), snapshot_id),
            )
    finally:
        connection.close()


def test_incomplete_capture_makes_m6_render_dependent_rules_unknown(tmp_path: Path) -> None:
    audit_id = "AUD-CAPTURE-M6"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="capture quality"))
        page = Page(
            page_id="PGE-CAPTURE-M6",
            audit_id=audit_id,
            normalized_url="https://example.test/app",
            discovered_url="https://example.test/app",
        )
        persistence.pages.add(page)
        raw = workspace.artifacts / "raw.html"
        rendered = workspace.artifacts / "rendered.html"
        raw.write_text("<html><body><div id='app'></div></body></html>", encoding="utf-8")
        rendered.write_text(
            "<html><body><main aria-busy='true'><div class='skeleton'></div></main></body></html>",
            encoding="utf-8",
        )
        snapshot = PageSnapshot(
            snapshot_id="SNP-CAPTURE-M6",
            page_id=page.page_id,
            device=DeviceContext.DESKTOP,
            requested_url=page.normalized_url,
            final_url=page.normalized_url,
            captured_at=_NOW,
            http_status=200,
            content_type="text/html",
            raw_artifact_ref=raw.relative_to(workspace.root).as_posix(),
            rendered_artifact_ref=rendered.relative_to(workspace.root).as_posix(),
            browser_metadata=_quality("INCOMPLETE"),
        )
        persistence.snapshots.add(snapshot)

        prior_ids: list[str] = []
        for rule_id in ("BR-GEO-005", "BR-GEO-006", "BR-GEO-009"):
            execution = RuleExecution(
                rule_execution_id=new_id("REX"),
                audit_id=audit_id,
                rule_id=rule_id,
                rule_version="1",
                page_id=page.page_id,
                snapshot_id=None,
                device=None,
                result=RuleResult.PASS,
                observed_value={},
                expected_condition="fixture",
                evidence_ids=(),
                executed_at=_NOW,
            )
            persistence.rule_executions.add(execution)
            prior_ids.append(execution.rule_execution_id)

        ids, findings, _classification, outside = execute_m6_snapshot_scope(
            audit_id=audit_id,
            page_id=page.page_id,
            snapshot_id=snapshot.snapshot_id,
            device=DeviceContext.DESKTOP,
            acquisition=SimpleNamespace(status=200, network_error=None),
            origin="https://example.test",
            audited_urls={page.normalized_url},
            persistence=persistence,
            workspace=workspace,
            prior=_PriorState(persistence, tuple(prior_ids)),
            resolver=DependencyResolver(),
            manager=EvidenceManager(persistence),
            writer=SnapshotArchitectureWriter(workspace),
            analyzer=JavascriptSpaAnalyzer(),
        )

        executions = [persistence.rule_executions.get(value) for value in ids]
        assert {item.result for item in executions if item is not None} == {RuleResult.UNKNOWN}
        assert all(
            item.observed_value == {"reason": "RENDER_CAPTURE_QUALITY_INCOMPLETE"}
            for item in executions
            if item is not None
        )
        assert findings == ()
        assert outside == frozenset()


def test_incomplete_capture_makes_content_extractability_unknown_without_findings(tmp_path: Path) -> None:
    audit_id = "AUD-CAPTURE-CONTENT"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        audit, m3, _m4, _m5, _m6, snapshot_id, _ = m7_fixture(workspace, persistence)
        snapshot = persistence.snapshots.get(snapshot_id)
        assert snapshot is not None
        connection = persistence._connection
        connection.execute(
            "UPDATE page_snapshots SET browser_metadata=? WHERE snapshot_id=?",
            (json.dumps(_quality("INCOMPLETE")), snapshot_id),
        )
        connection.commit()

        result = execute_content_extractability(
            audit_id=audit.audit_id,
            m3_result=m3,
            persistence=persistence,
            workspace=workspace,
        )
        executions = [persistence.rule_executions.get(value) for value in result.rule_execution_ids]
        assert {item.result for item in executions if item is not None} == {RuleResult.UNKNOWN}
        assert result.finding_ids == ()


def test_incomplete_capture_blocks_provider_and_reduces_semantic_coverage(tmp_path: Path) -> None:
    class Provider:
        name = "FAKE"

        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, _semantic_input):
            self.calls += 1
            return ProviderCallResult(ProviderState.AVAILABLE)

    audit_id = "AUD-CAPTURE-M7"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        audit, m3, m4, m5, m6, snapshot_id, _ = m7_fixture(workspace, persistence)
        connection = persistence._connection
        connection.execute(
            "UPDATE page_snapshots SET browser_metadata=? WHERE snapshot_id=?",
            (json.dumps(_quality("INCOMPLETE")), snapshot_id),
        )
        connection.commit()
        provider = Provider()

        result = execute_m7(
            audit_id=audit.audit_id,
            m3_result=m3,
            m4_result=m4,
            m5_result=m5,
            m6_result=m6,
            persistence=persistence,
            workspace=workspace,
            provider=provider,
        )

        assert provider.calls == 0
        executions = tuple(
            item
            for value in result.rule_execution_ids
            if (item := persistence.rule_executions.get(value)) is not None
        )
        assert executions
        assert {item.result for item in executions} == {RuleResult.UNKNOWN}
        assert result.finding_ids == ()

        scored = ScoringEngine().score(
            audit_id=audit.audit_id,
            executions=executions,
            devices=(DeviceContext.DESKTOP,),
        )
        semantic_dimension = _metadata("BR-GEO-028").dimension
        semantic_score = next(
            item
            for item in scored.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == semantic_dimension
        )
        assert semantic_score.coverage < 1.0
        assert semantic_score.confidence is not ScoreConfidence.HIGH


def test_core_projection_derives_limitation_and_selective_retry_from_persisted_quality(tmp_path: Path) -> None:
    workspace = core_workspace(
        tmp_path,
        render_succeeded=True,
        rendered_exists=True,
    )
    _set_snapshot_quality(workspace, "SNP-CORE", "INCOMPLETE")

    synchronize_core_work_items(workspace, "AUD-CORE-RECOVERY")

    items = _by_component(workspace)
    assert items[RENDER_CAPTURE].status == FAILED_RETRYABLE
    assert items[RENDER_CAPTURE].last_error_code == "RENDER_CAPTURE_QUALITY_INCOMPLETE"
    assert items[CONTENT_EXTRACTION].status == WAITING_FOR_DATA
    assert items[CONTENT_EXTRACTION].last_error_code == "RENDER_CAPTURE_QUALITY_REQUIRED"
    with AuditPersistence(workspace) as persistence:
        audit = persistence.audits.get("AUD-CORE-RECOVERY")
        assert audit is not None
        assert any(
            item.startswith("RENDER_CAPTURE_QUALITY_LIMITED:INCOMPLETE=1;UNAVAILABLE=0")
            for item in audit.limitations
        )


def test_legacy_snapshot_without_capture_quality_keeps_existing_projection(tmp_path: Path) -> None:
    workspace = core_workspace(
        tmp_path,
        render_succeeded=True,
        rendered_exists=True,
    )

    synchronize_core_work_items(workspace, "AUD-CORE-RECOVERY")

    items = _by_component(workspace)
    assert items[RENDER_CAPTURE].status == "SUCCESS"
    with AuditPersistence(workspace) as persistence:
        audit = persistence.audits.get("AUD-CORE-RECOVERY")
        assert audit is not None
        assert not any(
            item.startswith("RENDER_CAPTURE_QUALITY_LIMITED:")
            for item in audit.limitations
        )


def test_rpr_rejects_still_incomplete_replacement_without_overwriting_snapshot(tmp_path: Path) -> None:
    class Renderer:
        def render(self, url, device, **_kwargs):
            return BrowserRenderResult(
                requested_url=url,
                final_url=url,
                http_status=200,
                content_type="text/html",
                rendered_html="<html><body><main aria-busy='true'><div class='skeleton'></div></main></body></html>",
                screenshot_png=b"PNG",
                browser_metadata=_quality("INCOMPLETE"),
                error_kind=None,
            )

    workspace = core_workspace(
        tmp_path,
        render_succeeded=True,
        rendered_exists=True,
    )
    _set_snapshot_quality(workspace, "SNP-CORE", "INCOMPLETE")
    synchronize_core_work_items(workspace, "AUD-CORE-RECOVERY")
    item = _by_component(workspace)[RENDER_CAPTURE]

    before = sqlite3.connect(workspace.database)
    try:
        original = before.execute(
            "SELECT rendered_artifact_ref,browser_metadata FROM page_snapshots WHERE snapshot_id='SNP-CORE'"
        ).fetchone()
    finally:
        before.close()

    success, code, affected = _recover_render(
        workspace,
        "AUD-CORE-RECOVERY",
        item,
        "RPR-CAPTURE-QUALITY",
        Renderer(),
    )

    assert success is False
    assert code == "RENDER_CAPTURE_QUALITY_INCOMPLETE"
    assert affected == set()
    after = sqlite3.connect(workspace.database)
    try:
        current = after.execute(
            "SELECT rendered_artifact_ref,browser_metadata FROM page_snapshots WHERE snapshot_id='SNP-CORE'"
        ).fetchone()
    finally:
        after.close()
    assert current == original

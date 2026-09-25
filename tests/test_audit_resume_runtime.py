from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

import pytest

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    RUNNING,
    SUCCESS,
    begin_attempt,
    list_work_items,
    register_work_item,
)
from rasai.audit_resume_runtime import (
    _all_other_required_resolved,
    expected_devices_for_audit,
    finalize_resumed_audit,
    finish_execution_session,
    interrupted_core_projection,
    load_resume_plan,
    materialize_planned_work_items,
    persist_resume_plan,
    reconcile_interrupted_attempts,
    resume_plan_options,
    start_execution_session,
)
from rasai.core_reprocessing import (
    DISCOVERY_ACQUISITION,
    HTTP_ACQUISITION,
    RENDER_CAPTURE,
    _recover_discovery,
    _recover_render,
    _retryable_core,
    synchronize_core_work_items,
)
from rasai.domain import (
    Audit,
    AuditTarget,
    DeviceContext,
    Evidence,
    EvidenceType,
    Page,
    RuleExecution,
    RuleResult,
    TargetType,
    new_id,
    utc_now,
)
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import BrowserRenderResult
from rasai.reprocess_measurements import recover_experience_apdex, recover_synthetic_apdex


AUDIT_ID = "AUD-INTERRUPTED-RESUME"
URL = "https://example.test/"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    audit = Audit(audit_id=AUDIT_ID, project_name="resume", max_pages=3)
    target = AuditTarget(
        target_id="TGT-RESUME",
        audit_id=AUDIT_ID,
        input_url=URL,
        normalized_origin="https://example.test",
        target_type=TargetType.URL,
    )
    page = Page(
        page_id="PGE-RESUME",
        audit_id=AUDIT_ID,
        normalized_url=URL,
        discovered_url=URL,
    )
    http_evidence = Evidence(
        evidence_id=new_id("EV-GEO"),
        audit_id=AUDIT_ID,
        page_id=page.page_id,
        snapshot_id=None,
        device=None,
        evidence_type=EvidenceType.HTTP_RESPONSE,
        source="http",
        observed_value={
            "requested_url": URL,
            "final_url": URL,
            "status": 200,
            "headers": [["Content-Type", "text/html"]],
            "redirect_chain": [],
            "network_error": None,
            "elapsed_ms": 5,
        },
        artifact_reference=None,
        captured_at=utc_now(),
    )
    http_rule = RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id=AUDIT_ID,
        rule_id="BR-GEO-005",
        rule_version="1",
        page_id=page.page_id,
        snapshot_id=None,
        device=None,
        result=RuleResult.PASS,
        observed_value={"status": 200, "network_error": None},
        expected_condition="retrievable",
        evidence_ids=(http_evidence.evidence_id,),
        executed_at=utc_now(),
    )
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.targets.add(target)
        persistence.pages.add(page)
        persistence.evidence.add(http_evidence)
        persistence.rule_executions.add(http_rule)
    return workspace


def test_resume_plan_persists_device_universe_before_snapshots(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    plan = persist_resume_plan(
        workspace,
        AUDIT_ID,
        targets=(URL,),
        target_type="URL",
        language="pt-BR",
        market="BR",
        max_pages=3,
        device_context="both",
        content_remediation=False,
        technical_remediation=False,
    )

    assert plan["schema_version"] == "AUDIT-RESUME-001"
    assert expected_devices_for_audit(workspace, AUDIT_ID) == ("DESKTOP", "MOBILE")
    connection = sqlite3.connect(workspace.database)
    try:
        stored = connection.execute(
            "SELECT configuration FROM audit_fulfillment_contracts WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()
        assert stored is not None
        assert "resume_plan" in str(stored[0])
        assert "token" not in str(stored[0]).casefold()
    finally:
        connection.close()


def test_active_execution_session_blocks_concurrent_resume(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = start_execution_session(
        workspace,
        AUDIT_ID,
        kind="INITIAL",
        source="TEST",
        reject_active=False,
    )
    try:
        with pytest.raises(RuntimeError, match="execução ativa"):
            start_execution_session(
                workspace,
                AUDIT_ID,
                kind="REPROCESS",
                source="TEST",
                reject_active=True,
            )
    finally:
        finish_execution_session(workspace, first, state="COMPLETED")

    second = start_execution_session(
        workspace,
        AUDIT_ID,
        kind="REPROCESS",
        source="TEST",
        reject_active=True,
    )
    finish_execution_session(workspace, second, state="COMPLETED")


def test_orphan_running_attempt_is_closed_and_item_becomes_retryable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="TEST_COMPONENT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
    )
    attempt_id = begin_attempt(
        workspace,
        audit_id=AUDIT_ID,
        component="TEST_COMPONENT",
    )
    assert any(
        item.component == "TEST_COMPONENT" and item.status == RUNNING
        for item in list_work_items(workspace, AUDIT_ID)
    )

    assert reconcile_interrupted_attempts(workspace, AUDIT_ID) == 1

    item = next(
        item for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "TEST_COMPONENT"
    )
    assert item.status == FAILED_RETRYABLE
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT status,error_code,finished_at FROM audit_fulfillment_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "INTERRUPTED"
        assert row[1] == "ATTEMPT_ABANDONED"
        assert row[2]
    finally:
        connection.close()


def test_orphan_running_with_persisted_http_result_reconciles_without_retry(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=HTTP_ACQUISITION,
        scope_key="PGE-RESUME",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
        configuration={"page_id": "PGE-RESUME", "url": URL},
    )
    begin_attempt(
        workspace,
        audit_id=AUDIT_ID,
        component=HTTP_ACQUISITION,
        scope_key="PGE-RESUME",
    )

    assert reconcile_interrupted_attempts(workspace, AUDIT_ID) == 1
    synchronize_core_work_items(workspace, AUDIT_ID)

    http_item = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == HTTP_ACQUISITION and item.scope_key == "PGE-RESUME"
    )
    assert http_item.status == SUCCESS
    assert all(
        not (
            item.component == HTTP_ACQUISITION
            and item.scope_key == "PGE-RESUME"
        )
        for item in _retryable_core(workspace, AUDIT_ID)
    )


def test_cancelled_audit_with_durable_plan_is_retryable_core(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    persist_resume_plan(
        workspace,
        AUDIT_ID,
        targets=(URL,),
        target_type="URL",
        language="pt-BR",
        market="BR",
        max_pages=3,
        device_context="mobile",
        content_remediation=False,
        technical_remediation=False,
    )
    status, retryable = interrupted_core_projection(workspace, AUDIT_ID, "CANCELLED")
    assert status == FAILED_RETRYABLE
    assert retryable is True


def test_missing_configured_render_context_is_materialized_and_recovered(tmp_path: Path) -> None:
    class Renderer:
        def render(self, url, device, **kwargs):
            assert url == URL
            assert device is DeviceContext.MOBILE
            return BrowserRenderResult(
                requested_url=url,
                final_url=url,
                http_status=200,
                content_type="text/html",
                rendered_html="<html><body><main>resume</main></body></html>",
                browser_metadata={"render_succeeded": True},
                error_kind=None,
            )

    workspace = _workspace(tmp_path)
    persist_resume_plan(
        workspace,
        AUDIT_ID,
        targets=(URL,),
        target_type="URL",
        language="pt-BR",
        market="BR",
        max_pages=3,
        device_context="mobile",
        content_remediation=False,
        technical_remediation=False,
    )

    synchronize_core_work_items(workspace, AUDIT_ID)
    planned = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == RENDER_CAPTURE and item.configuration.get("planned")
    )
    assert planned.scope_key == "PLANNED:PGE-RESUME:MOBILE"

    from rasai.audit_fulfillment import start_reprocess_run

    reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")
    success, code, affected = _recover_render(
        workspace,
        AUDIT_ID,
        planned,
        reprocess_id,
        Renderer(),
    )

    assert success is True
    assert code == "PLANNED_RENDER_CAPTURE_RECOVERED"
    assert len(affected) == 1
    snapshot_id = next(iter(affected))

    synchronize_core_work_items(workspace, AUDIT_ID)
    items = list_work_items(workspace, AUDIT_ID)
    planned_after = next(item for item in items if item.scope_key == planned.scope_key)
    actual = next(
        item
        for item in items
        if item.component == RENDER_CAPTURE and item.scope_key == snapshot_id
    )
    assert planned_after.status == SUCCESS
    assert actual.status == SUCCESS


def test_empty_interrupted_audit_cannot_be_finalized_before_discovery(tmp_path: Path) -> None:
    audit_id = "AUD-EMPTY-INTERRUPTED"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    audit = Audit(audit_id=audit_id, project_name="empty resume")
    target = AuditTarget(
        target_id="TGT-EMPTY",
        audit_id=audit_id,
        input_url=URL,
        normalized_origin="https://example.test",
        target_type=TargetType.URL,
    )
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.targets.add(target)
    persist_resume_plan(
        workspace,
        audit_id,
        targets=(URL,),
        target_type="URL",
        language="pt-BR",
        market="BR",
        max_pages=3,
        device_context="mobile",
        content_remediation=False,
        technical_remediation=False,
    )

    synchronize_core_work_items(workspace, audit_id)

    discovery = next(
        item
        for item in list_work_items(workspace, audit_id)
        if item.component == DISCOVERY_ACQUISITION
    )
    assert discovery.status == FAILED_RETRYABLE
    assert _all_other_required_resolved(workspace, audit_id) is False


def test_partial_discovery_is_archived_before_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    persist_resume_plan(
        workspace,
        AUDIT_ID,
        targets=(URL,),
        target_type="URL",
        language="pt-BR",
        market="BR",
        max_pages=3,
        device_context="mobile",
        content_remediation=False,
        technical_remediation=False,
    )

    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=DISCOVERY_ACQUISITION,
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=FAILED_RETRYABLE,
        retryable=True,
    )
    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == DISCOVERY_ACQUISITION
    )

    def fake_execute_m2(audit, target, persistence, workspace_arg, **kwargs):
        assert audit.audit_id == AUDIT_ID
        assert target.audit_id == AUDIT_ID
        assert workspace_arg.root == workspace.root
        assert kwargs.get("explicit_urls") is None
        persistence.pages.add(
            Page(
                page_id="PGE-REPLAYED",
                audit_id=AUDIT_ID,
                normalized_url=URL,
                discovered_url=URL,
            )
        )
        return type("M2Result", (), {"page_ids": ("PGE-REPLAYED",)})()

    import rasai.m2 as m2_module

    monkeypatch.setattr(m2_module, "execute_m2", fake_execute_m2)
    from rasai.audit_fulfillment import start_reprocess_run

    reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")
    success, code, affected = _recover_discovery(
        workspace,
        AUDIT_ID,
        item,
        reprocess_id,
    )

    assert success is True
    assert code == "DISCOVERY_ACQUISITION_RECOVERED"
    assert affected == set()

    connection = sqlite3.connect(workspace.database)
    try:
        pages = connection.execute(
            "SELECT page_id FROM pages WHERE audit_id=? ORDER BY page_id",
            (AUDIT_ID,),
        ).fetchall()
        archived = connection.execute(
            """SELECT entity_type,entity_id FROM audit_reprocess_derived_archive
               WHERE audit_id=? AND reprocess_id=? ORDER BY entity_type,entity_id""",
            (AUDIT_ID, reprocess_id),
        ).fetchall()
    finally:
        connection.close()

    assert pages == [("PGE-REPLAYED",)]
    assert ("partial_m2_page", "PGE-RESUME") in archived


def test_resume_rebuilds_partial_final_derivations_before_core_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        scope_key="AUDIT",
        required=True,
        status=FAILED_RETRYABLE,
        retryable=True,
    )

    # Simulate a process dying in M9 after one score row was persisted. Presence of a
    # score must not be treated as proof that scoring + recommendations completed.
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scores(score_id TEXT PRIMARY KEY,audit_id TEXT)"
            )
            connection.execute(
                "INSERT INTO scores(score_id,audit_id) VALUES(?,?)",
                ("SCR-PARTIAL", AUDIT_ID),
            )
    finally:
        connection.close()

    calls: list[tuple[str, str]] = []

    def recompute(*, workspace, audit_id, reprocess_id, semantic_changed):
        calls.append((audit_id, reprocess_id))

    import rasai.reprocess_ai as reprocess_ai

    monkeypatch.setattr(reprocess_ai, "recompute_derived_after_ai", recompute)

    assert finalize_resumed_audit(
        workspace,
        AUDIT_ID,
        reprocess_id="RPR-PARTIAL-DERIVED",
    ) is True
    assert calls == [(AUDIT_ID, "RPR-PARTIAL-DERIVED")]
    core = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "CORE_AUDIT"
    )
    assert core.status == SUCCESS


def test_resume_guard_closes_session_before_final_catalog_projection() -> None:
    from rasai import audit_resume_runtime

    source = Path(audit_resume_runtime.__file__).read_text(encoding="utf-8")
    start = source.index("def install()")
    block = source[start:]

    finish = block.index('finish_execution_session(workspace, session, state="COMPLETED")')
    projection = block.index("materialize_catalog_report_projection(", finish)
    assert finish < projection


def test_resume_plan_persists_effective_optional_intent_without_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("RASAI_IMPROVEMENT_INTELLIGENCE", "true")
    monkeypatch.setenv("RASAI_IMPROVEMENT_AI_PROVIDER", "openai")
    monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "secret-that-must-not-be-persisted")
    monkeypatch.setenv("RASAI_GSC_ENABLED", "true")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", "sc-domain:example.test")

    with resume_plan_options(
        {
            "web_performance": {
                "enabled": True,
                "max_pages": 3,
                "timeout_seconds": 90.0,
                "categories": ["performance", "seo"],
                "field_source": "auto",
                "pagespeed_key_configured": True,
                "crux_key_configured": False,
            },
            "synthetic_apdex": {
                "enabled": True,
                "threshold_seconds": 2.0,
                "target_valid_samples": 10,
                "max_attempts_per_context": 13,
                "max_pages": 1,
                "timeout_seconds": 45.0,
                "delay_seconds": 1.0,
                "concurrency": 1,
            },
            "search_intelligence": {
                "enabled": True,
                "queries": ["rasai readiness"],
                "mode": "live",
                "provider": "serpapi",
                "max_queries": 10,
                "max_requests": 10,
                "max_depth": 20,
                "max_competitors": 10,
                "timeout_seconds": 20.0,
                "retries": 1,
                "min_interval_seconds": 1.0,
            },
        }
    ):
        persist_resume_plan(
            workspace,
            AUDIT_ID,
            targets=(URL,),
            target_type="URL",
            language="pt-BR",
            market="BR",
            max_pages=3,
            device_context="mobile",
            content_remediation=True,
            technical_remediation=True,
            semantic_ai_requested=True,
            semantic_provider="AUTO",
        )

    plan = load_resume_plan(workspace, AUDIT_ID)
    serialized = str(plan)
    assert "secret-that-must-not-be-persisted" not in serialized
    assert plan["semantic_ai_requested"] is True
    assert plan["execution_options"]["web_performance"]["enabled"] is True
    assert plan["execution_options"]["search_intelligence"]["queries"] == ["rasai readiness"]
    assert plan["optional_environment"]["RASAI_GSC_ENABLED"] == "true"
    assert "RASAI_SERPAPI_API_KEY" not in plan["optional_environment"]

    materialize_planned_work_items(workspace, AUDIT_ID)
    items = {
        (item.component, item.scope_key): item
        for item in list_work_items(workspace, AUDIT_ID)
    }
    for component in (
        "WEB_PERFORMANCE",
        "SYNTHETIC_APDEX",
        "SEARCH_INTELLIGENCE",
        "TECHNICAL_AI",
        "CONTENT_REMEDIATION_AI",
        "IMPROVEMENT_INTELLIGENCE",
        "GOOGLE_SEARCH_CONSOLE",
    ):
        assert (component, "AUDIT") in items
        assert items[(component, "AUDIT")].status == "REQUESTED_NOT_EXECUTED"




def test_planned_navigation_apdex_can_start_during_resume_without_prior_run_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SYNTHETIC_APDEX",
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=FAILED_RETRYABLE,
        retryable=True,
        configuration={
            "enabled": True,
            "threshold_seconds": 2.0,
            "target_valid_samples": 10,
            "max_attempts_per_context": 13,
            "max_pages": 1,
            "timeout_seconds": 45.0,
            "delay_seconds": 1.0,
            "concurrency": 1,
        },
    )
    item = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "SYNTHETIC_APDEX"
    )
    captured = {}

    import rasai.m23_apdex as m23

    def fake_execute(*, audit_id, workspace, config, **_kwargs):
        captured["audit_id"] = audit_id
        captured["config"] = config
        return type("Result", (), {"status": "SUCCESS"})()

    monkeypatch.setattr(m23, "execute_m23_apdex", fake_execute)

    assert recover_synthetic_apdex(
        workspace=workspace,
        audit_id=AUDIT_ID,
        item=item,
    ) is True
    assert captured["audit_id"] == AUDIT_ID
    assert captured["config"].target_valid_samples == 10
    assert captured["config"].threshold_seconds == 2.0


def test_planned_experience_apdex_can_start_during_resume_without_prior_run_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="EXPERIENCE_APDEX",
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=FAILED_RETRYABLE,
        retryable=True,
        configuration={
            "enabled": True,
            "target_samples_per_page": 10,
            "max_attempts_per_page": 13,
            "max_pages": 1,
            "device_mix": {"MOBILE": 60.0, "DESKTOP": 40.0},
            "session_mode": "cold",
            "kpm": "USER_ACTION_DURATION",
            "satisfied_threshold_seconds": 2.0,
            "frustrated_threshold_seconds": 8.0,
            "errors_affect_apdex": True,
            "error_scope": "first-party",
            "settle_seconds": 5.0,
            "delay_seconds": 1.0,
            "concurrency": 1,
        },
    )
    item = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "EXPERIENCE_APDEX"
    )
    captured = {}

    import rasai.m25_apdex_experience as m25

    def fake_execute(*, audit_id, workspace, config, **_kwargs):
        captured["audit_id"] = audit_id
        captured["config"] = config
        return type("Result", (), {"status": "SUCCESS"})()

    monkeypatch.setattr(m25, "execute_m25_experience", fake_execute)

    assert recover_experience_apdex(
        workspace=workspace,
        audit_id=AUDIT_ID,
        item=item,
    ) is True
    assert captured["audit_id"] == AUDIT_ID
    assert captured["config"].target_samples_per_page == 10
    assert captured["config"].device_mix_dict() == {"MOBILE": 60.0, "DESKTOP": 40.0}



from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai import audit_phase_runtime
from rasai import governed_reprocess_runtime as runtime
from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    list_work_items,
    recalculate,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_reprocess import ReprocessResult
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.selective_reprocess_context import scope


AUDIT_ID = "AUD-RPR-DEPENDENCIES"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="RPR dependency test"))
    initialize_contract(workspace, AUDIT_ID)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=False,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{AUDIT_ID}",
        retryable=False,
    )
    return workspace


def _register_pending(
    workspace: AuditWorkspace,
    component: str,
    *,
    temporal_mode: str = REPLAY_SAFE,
    valid_until: str | None = None,
) -> None:
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        required=True,
        temporal_mode=temporal_mode,
        status=FAILED_RETRYABLE,
        retryable=True,
        valid_until=valid_until,
        configuration={"requested": True},
    )


def test_registered_advisory_ai_waits_for_primary_required_ai(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "SEMANTIC_AI")
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")

    assert runtime._registered_ai_purposes(workspace, AUDIT_ID, {}) == frozenset()

    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        status=SUCCESS,
        result_ref="semantic:effective",
    )

    assert runtime._registered_ai_purposes(
        workspace,
        AUDIT_ID,
        {"SEARCH_INTELLIGENCE": "SUCCESS"},
    ) == frozenset({"IMPROVEMENT_INTELLIGENCE", "COMPETITIVE_INTELLIGENCE"})


def test_live_measurement_expiry_prevents_external_retry(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(
        workspace,
        "WEB_PERFORMANCE",
        temporal_mode=LIVE_RECOLLECTION,
        valid_until="2000-01-01T00:00:00+00:00",
    )

    from rasai import reprocess_measurements

    monkeypatch.setattr(
        reprocess_measurements,
        "recover_web_performance",
        lambda **_kwargs: pytest.fail("expired Web Performance must not call integration"),
    )

    assert runtime._recover_live_measurements(workspace, AUDIT_ID) == {}


def test_optional_recovery_never_refreshes_nonblocking_observability(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "GOOGLE_SEARCH_CONSOLE", temporal_mode=LIVE_RECOLLECTION)

    calls: list[str] = []

    def registered(name: str):
        calls.append(name)
        assert name != "EXTERNAL_OBSERVABILITY"

        def collect(**_kwargs):
            return {"collection_state": "SUCCESS", "service_state": "SUCCESS"}

        return collect

    from rasai import selective_optional_reprocess as optional

    monkeypatch.setattr(runtime, "_registered_collector", registered)
    monkeypatch.setattr(optional, "_original_optional_environment", lambda *_args: nullcontext())

    def reconcile(workspace: AuditWorkspace, audit_id: str) -> None:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="GOOGLE_SEARCH_CONSOLE",
            status=SUCCESS,
            result_ref="gsc:effective",
            retryable=False,
        )

    monkeypatch.setattr(optional, "_reconcile_gsc_rpr", reconcile)

    states, evaluated = runtime._recover_optional_collectors(workspace, AUDIT_ID)

    assert calls == ["GOOGLE_SEARCH_CONSOLE"]
    assert states == {"GOOGLE_SEARCH_CONSOLE": "SUCCESS"}
    assert evaluated == frozenset({"GOOGLE_SEARCH_CONSOLE"})


def test_registered_ai_filter_executes_only_selected_purpose(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audit_phase_runtime, "_AI_HOOKS", {})
    calls: list[str] = []

    def hook_a(**_kwargs):
        calls.append("A")
        return {"status": "COMPLETE"}

    def hook_b(**_kwargs):
        calls.append("B")
        return {"status": "COMPLETE"}

    audit_phase_runtime.register_ai_hook("A", hook_a, order=10)
    audit_phase_runtime.register_ai_hook("B", hook_b, order=20)

    outcomes = audit_phase_runtime.run_registered_ai_phase(
        audit_id=AUDIT_ID,
        workspace=SimpleNamespace(root=tmp_path),
        evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
        purposes={"A"},
    )

    assert calls == ["A"]
    assert set(outcomes) == {"A"}


def test_governed_final_order_is_ai_data_strategy_catalog(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")
    events: list[str] = []

    def run_ai(**kwargs):
        events.append("registered-ai")
        assert kwargs["purposes"] == frozenset({"IMPROVEMENT_INTELLIGENCE"})
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component="IMPROVEMENT_INTELLIGENCE",
            status=SUCCESS,
            result_ref="improvement:effective",
            retryable=False,
        )
        return {"IMPROVEMENT_INTELLIGENCE": {"status": "COMPLETE"}}

    monkeypatch.setattr(runtime, "run_registered_ai_phase", run_ai)
    monkeypatch.setattr(runtime, "mark_ai_sealed", lambda **_kwargs: events.append("ai-sealed"))
    monkeypatch.setattr(
        runtime,
        "project_report_validity",
        lambda **_kwargs: events.append("report-validity"),
    )

    preparation = runtime.ReprocessPreparation(
        snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
        recovered={},
        evaluated_optional=frozenset(),
        sealed_new_evidence=False,
    )

    runtime._registered_ai_and_report(
        workspace=workspace,
        audit_id=AUDIT_ID,
        preparation=preparation,
        data_finalizer=lambda **_kwargs: events.append("data-finalizer"),
        directed_finalizer=lambda **_kwargs: events.append("directed-analysis"),
        catalog_finalizer=lambda **_kwargs: events.append("report-catalog"),
    )

    assert recalculate(workspace, AUDIT_ID).processing_status == "COMPLETE"
    assert events == [
        "registered-ai",
        "ai-sealed",
        "data-finalizer",
        "directed-analysis",
        "report-catalog",
        "report-validity",
    ]


def test_complete_aud_is_true_noop_before_any_rpr_integration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    from rasai import core_reprocessing

    monkeypatch.setattr(core_reprocessing, "_wrap_reprocess", lambda original, _module: original)
    runtime._install_core_composition()
    wrapped_factory = core_reprocessing._wrap_reprocess

    def fail_start(*_args, **_kwargs):
        pytest.fail("complete AUD must not start an RPR")

    fake_module = SimpleNamespace(
        _latest_pending=lambda active_workspace, active_audit_id: tuple(
            item
            for item in list_work_items(active_workspace, active_audit_id, pending_only=True)
            if item.required
        ),
        start_reprocess_run=fail_start,
        finish_reprocess_run=lambda *_args, **_kwargs: recalculate(workspace, AUDIT_ID),
    )
    calls: list[str] = []

    def base(audit_id: str, *, audits_root: str | Path, source: str):
        calls.append("base-noop")
        return ReprocessResult(
            audit_id=audit_id,
            reprocess_id=None,
            processing_status="COMPLETE",
            score_status="FINAL",
            report_status="FINAL",
            consolidation_eligible=True,
            attempted_items=0,
            successful_items=0,
            skipped_success_items=1,
            remaining_items=0,
            temporal_expired_items=0,
            report_root=workspace.root / "report-catalog",
        )

    downstream = wrapped_factory(base, fake_module)
    result = downstream(AUDIT_ID, audits_root=tmp_path, source="TEST")

    assert calls == ["base-noop"]
    assert result.attempted_items == 0


def test_rpr_data_finalizers_do_not_recall_external_integrations(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    from rasai import report_completion
    from rasai import standards_gsc_observability_runtime as gsc
    from rasai import external_observability_runtime as external
    from rasai import standards_css_validation as css

    base = lambda **_kwargs: report_completion.AuditReportCompletion((), (), ())

    for marker in (
        "_rasai_gsc_observability_runtime",
        "_rasai_external_observability_runtime",
        "_rasai_css_validation_runtime",
    ):
        monkeypatch.delattr(report_completion, marker, raising=False)

    monkeypatch.setattr(report_completion, "finalize_audit_report_site", base)
    monkeypatch.setattr(
        gsc,
        "collect_configured_search_console",
        lambda **_kwargs: pytest.fail("GSC must not be called from RPR finalization"),
    )
    gsc.install()

    monkeypatch.setattr(
        external,
        "collect_configured_external_observability",
        lambda **_kwargs: pytest.fail("external observability must not be refreshed by RPR finalization"),
    )
    external.install()

    monkeypatch.setattr(
        css,
        "collect_css_validation",
        lambda **_kwargs: pytest.fail("CSS validator must not be called from RPR finalization"),
    )
    css.install()

    with scope(AUDIT_ID, {"GOOGLE_SEARCH_CONSOLE"}, workspace=workspace):
        result = report_completion.finalize_audit_report_site(
            audit_id=AUDIT_ID,
            workspace=workspace,
        )

    assert result.complete is True


def test_reprocess_material_fingerprint_ignores_volatile_timestamps_but_detects_result_change(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            """CREATE TABLE web_performance_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                status TEXT NOT NULL,
                captured_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?)",
            ("OBS-1", AUDIT_ID, "PARTIAL", "2026-09-19T10:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()

    original = runtime._material_state_fingerprint(workspace, AUDIT_ID)

    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            "UPDATE web_performance_observations SET captured_at=? WHERE observation_id='OBS-1'",
            ("2026-09-19T10:05:00Z",),
        )
        connection.commit()
    finally:
        connection.close()
    assert runtime._material_state_fingerprint(workspace, AUDIT_ID) == original

    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            "UPDATE web_performance_observations SET status='SUCCESS' WHERE observation_id='OBS-1'"
        )
        connection.commit()
    finally:
        connection.close()
    assert runtime._material_state_fingerprint(workspace, AUDIT_ID) != original


def test_prepare_reprocess_reuses_evidence_snapshot_when_nothing_material_changed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    from rasai.ai_governance import seal_evidence

    prior = seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        context={"phase": "INITIAL"},
    )
    monkeypatch.setattr(runtime, "_recover_live_measurements", lambda *_args: {})
    monkeypatch.setattr(
        runtime,
        "_recover_optional_collectors",
        lambda *_args: ({}, frozenset()),
    )
    monkeypatch.setattr(runtime, "_recover_impacted_deterministic", lambda *_args: {})

    preparation = runtime._prepare_reprocess(workspace, AUDIT_ID)

    assert preparation.snapshot.evidence_snapshot_id == prior.evidence_snapshot_id
    assert preparation.sealed_new_evidence is False


@pytest.mark.parametrize(
    ("before", "after", "expected_external"),
    [
        ((("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),), (("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),), 0),
        ((("CMP-1", "jquery", "3.6.0", "npm", "MEDIUM"),), (("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),), 1),
    ],
)
def test_passive_security_rpr_refreshes_external_intelligence_only_when_components_change(
    monkeypatch,
    tmp_path: Path,
    before,
    after,
    expected_external: int,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "PASSIVE_SECURITY")
    signatures = iter((before, after))
    monkeypatch.setattr(
        runtime,
        "_passive_component_signature",
        lambda *_args, **_kwargs: next(signatures),
    )
    monkeypatch.setattr(runtime, "_archive_passive_security", lambda *_args: None)

    from rasai import passive_security as security
    from rasai import selective_optional_reprocess as optional

    monkeypatch.setattr(optional, "_original_optional_environment", lambda *_args: nullcontext())
    external_calls: list[str] = []
    monkeypatch.setattr(
        security,
        "collect_external_intelligence",
        lambda **_kwargs: external_calls.append("external") or {"collection_state": "SUCCESS"},
    )
    monkeypatch.setattr(
        security,
        "analyze_passive_security",
        lambda **_kwargs: {"status": "COMPLETED"},
    )

    states = runtime._recover_impacted_deterministic(workspace, AUDIT_ID)

    assert states == {"PASSIVE_SECURITY": "SUCCESS"}
    assert len(external_calls) == expected_external
    item = next(
        item for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "PASSIVE_SECURITY"
    )
    assert item.status == SUCCESS


def test_governed_dependency_invalidation_reopens_only_impacted_success(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for component in ("PASSIVE_SECURITY", "WEB_PERFORMANCE"):
        register_work_item(
            workspace,
            audit_id=AUDIT_ID,
            component=component,
            required=True,
            temporal_mode=REPLAY_SAFE,
            status=SUCCESS,
            retryable=False,
        )
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component=component,
            status=SUCCESS,
            result_ref=f"{component.casefold()}:effective",
            retryable=False,
        )

    from rasai.governed_fulfillment_invalidation import invalidate_work_item

    changed = invalidate_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        error_class="EVIDENCE_DEPENDENCY",
        error_code="PASSIVE_SECURITY_INPUT_CHANGED",
        error_message="core evidence changed",
    )

    assert changed is True
    items = {item.component: item for item in list_work_items(workspace, AUDIT_ID)}
    assert items["PASSIVE_SECURITY"].status == FAILED_RETRYABLE
    assert items["PASSIVE_SECURITY"].retryable is True
    assert items["PASSIVE_SECURITY"].effective_result_ref == "passive_security:effective"
    assert items["WEB_PERFORMANCE"].status == SUCCESS
    assert items["WEB_PERFORMANCE"].effective_result_ref == "web_performance:effective"

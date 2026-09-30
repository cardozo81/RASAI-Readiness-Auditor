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
    begin_attempt,
    finish_attempt,
    initialize_contract,
    list_work_items,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.audit_reprocess import ReprocessResult
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_policy import item_key, reprocess_policy
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


def test_improvement_rpr_uses_same_required_fulfillment_gate_as_initial_audit(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status="PENDING",
        retryable=True,
    )
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")

    assert runtime._registered_ai_purposes(
        workspace,
        AUDIT_ID,
        {},
    ) == frozenset()

    improvement = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "IMPROVEMENT_INTELLIGENCE"
    )
    assert improvement.status == "WAITING_FOR_DATA"
    assert "SEMANTIC_AI" in str(improvement.last_error_message)

    # Competitive analysis remains independent; only Improvement shares the full
    # Deep Analysis fulfillment gate from the initial AUD.
    assert runtime._registered_ai_purposes(
        workspace,
        AUDIT_ID,
        {"SEARCH_INTELLIGENCE": "SUCCESS"},
    ) == frozenset({"COMPETITIVE_INTELLIGENCE"})


def test_improvement_rpr_accepts_same_terminal_degraded_dependency_as_initial_gate(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "SEMANTIC_AI")  # FAILED_RETRYABLE is terminal for the AI snapshot.
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")

    assert runtime._registered_ai_purposes(
        workspace,
        AUDIT_ID,
        {},
    ) == frozenset({"IMPROVEMENT_INTELLIGENCE"})


def test_live_measurement_without_adapter_attempt_gets_generic_rpr_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(
        workspace,
        "WEB_PERFORMANCE",
        temporal_mode=LIVE_RECOLLECTION,
        valid_until="2099-01-01T00:00:00+00:00",
    )
    reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")

    from rasai import reprocess_measurements

    monkeypatch.setattr(
        reprocess_measurements,
        "recover_web_performance",
        lambda **_kwargs: True,
    )

    states = runtime._recover_live_measurements(workspace, AUDIT_ID)

    assert states == {"WEB_PERFORMANCE": "SUCCESS"}
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT a.reprocess_id,a.attempt_number,a.status
               FROM audit_fulfillment_attempts a
               JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id
               WHERE w.audit_id=? AND w.component='WEB_PERFORMANCE'""",
            (AUDIT_ID,),
        ).fetchall()
        item = connection.execute(
            """SELECT attempt_count,status
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='WEB_PERFORMANCE'""",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()

    assert rows == [(reprocess_id, 1, "SUCCESS")]
    assert item == (1, "SUCCESS")


def test_live_measurement_adopts_adapter_attempt_without_double_counting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(
        workspace,
        "SYNTHETIC_APDEX",
        temporal_mode=LIVE_RECOLLECTION,
        valid_until="2099-01-01T00:00:00+00:00",
    )
    reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")

    from rasai import reprocess_measurements

    def recover_with_internal_attempt(**_kwargs):
        attempt_id = begin_attempt(
            workspace,
            audit_id=AUDIT_ID,
            component="SYNTHETIC_APDEX",
            reprocess_id=None,
            metadata={"source": "adapter"},
        )
        finish_attempt(
            workspace,
            attempt_id,
            status=SUCCESS,
            result_ref="synthetic-apdex:adapter-success",
        )
        return True

    monkeypatch.setattr(
        reprocess_measurements,
        "recover_synthetic_apdex",
        recover_with_internal_attempt,
    )

    states = runtime._recover_live_measurements(workspace, AUDIT_ID)

    assert states == {"SYNTHETIC_APDEX": "SUCCESS"}
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT a.reprocess_id,a.attempt_number,a.status,a.metadata
               FROM audit_fulfillment_attempts a
               JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id
               WHERE w.audit_id=? AND w.component='SYNTHETIC_APDEX'
               ORDER BY a.attempt_number""",
            (AUDIT_ID,),
        ).fetchall()
        item = connection.execute(
            """SELECT attempt_count,status
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='SYNTHETIC_APDEX'""",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0][0] == reprocess_id
    assert rows[0][1] == 1
    assert rows[0][2] == "SUCCESS"
    assert item == (1, "SUCCESS")


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


def test_live_measurement_waits_for_pending_render_without_calling_adapter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="RENDER_CAPTURE",
        scope_key="PLANNED:PGE-1:MOBILE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status="PENDING",
        retryable=True,
        configuration={"page_id": "PGE-1", "device": "MOBILE", "planned": True},
    )
    _register_pending(
        workspace,
        "WEB_PERFORMANCE",
        temporal_mode=LIVE_RECOLLECTION,
        valid_until="2099-01-01T00:00:00+00:00",
    )

    from rasai import reprocess_measurements

    monkeypatch.setattr(
        reprocess_measurements,
        "recover_web_performance",
        lambda **_kwargs: pytest.fail(
            "Web Performance must not run before rendered context is available"
        ),
    )

    with reprocess_policy(
        selected_items=[
            item_key("WEB_PERFORMANCE", "AUDIT"),
            "RENDER_CAPTURE",
        ],
        use_ai=False,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        states = runtime._recover_live_measurements(workspace, AUDIT_ID)

    assert states == {"WEB_PERFORMANCE": "WAITING_FOR_DATA"}
    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == "WEB_PERFORMANCE"
    )
    assert item.status == "WAITING_FOR_DATA"
    assert item.last_error_code == "REPROCESS_PREREQUISITES_INCOMPLETE"
    assert "RENDER_CAPTURE/PLANNED:PGE-1:MOBILE" in str(item.last_error_message)
    assert item.attempt_count == 0


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


def test_no_ai_mode_authorizes_data_recovery_but_no_registered_ai_purpose(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")
    _register_pending(workspace, "RENDER_CAPTURE", temporal_mode=LIVE_RECOLLECTION)

    with reprocess_policy(
        selected_items=[item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")],
        use_ai=False,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        assert runtime._registered_ai_purposes(workspace, AUDIT_ID, {}) == frozenset()
        render = next(
            item
            for item in list_work_items(workspace, AUDIT_ID)
            if item.component == "RENDER_CAPTURE"
        )
        from rasai.reprocess_policy import item_selected, item_executable

        assert item_selected(render) is True
        assert item_executable(render) is True
        improvement = next(
            item
            for item in list_work_items(workspace, AUDIT_ID)
            if item.component == "IMPROVEMENT_INTELLIGENCE"
        )
        assert item_selected(improvement) is True
        assert item_executable(improvement) is False


def test_improvement_ai_waits_for_unresolved_prerequisite_before_provider_phase(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _register_pending(workspace, "IMPROVEMENT_INTELLIGENCE")
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="RENDER_CAPTURE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status="PENDING",
        retryable=True,
    )

    purposes = runtime._registered_ai_purposes(workspace, AUDIT_ID, {})

    assert purposes == frozenset()
    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == "IMPROVEMENT_INTELLIGENCE"
    )
    assert item.status == "WAITING_FOR_DATA"
    assert item.last_error_class == "PREREQUISITE"
    assert item.last_error_code == "AI_WAITING_FOR_PREREQUISITES"
    assert "RENDER_CAPTURE" in str(item.last_error_message)


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


def test_deferred_catalog_projection_returns_completion_contract_without_rendering(
    monkeypatch,
) -> None:
    from rasai import directed_analysis, report_completion

    calls: list[str] = []
    original_catalog = report_completion.materialize_catalog_report_projection
    monkeypatch.setattr(
        report_completion,
        "materialize_catalog_report_projection",
        lambda **_kwargs: calls.append("catalog") or report_completion.AuditReportCompletion(
            expected_pages=("index.html",),
            generated_pages=("index.html",),
            missing_pages=(),
            renderer_errors=(),
        ),
    )
    monkeypatch.setattr(
        report_completion,
        "finalize_audit_report_site",
        lambda **_kwargs: calls.append("data-finalizer"),
    )
    monkeypatch.setattr(
        directed_analysis,
        "reprocess_directed_analysis",
        lambda **_kwargs: calls.append("directed"),
    )

    with runtime._defer_mid_reprocess_projection():
        completion = report_completion.materialize_catalog_report_projection(
            audit_id=AUDIT_ID,
            workspace=SimpleNamespace(),
        )
        assert completion.renderer_errors == ()
        assert completion.generated_pages == ()
        assert calls == []

    # The real callables are restored after the boundary. The exact catalog callable
    # is the test replacement captured by the context manager, not the module original.
    assert report_completion.materialize_catalog_report_projection is not original_catalog
    report_completion.materialize_catalog_report_projection(
        audit_id=AUDIT_ID,
        workspace=SimpleNamespace(),
    )
    assert calls == ["catalog"]


def test_governed_pre_finish_order_defers_catalog_projection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    # This test validates the post-collection AI/report ordering: represent
    # an actually completed acquisition contract, not a zero-collector AUD.
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="DISCOVERY_ACQUISITION",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=SUCCESS,
        retryable=False,
    )
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

    monkeypatch.setattr(runtime, "_archive_improvement_intelligence", lambda *_args: events.append("archive-improvement") or 1)
    monkeypatch.setattr(runtime, "run_registered_ai_phase", run_ai)
    monkeypatch.setattr(runtime, "mark_ai_sealed", lambda **_kwargs: events.append("ai-sealed"))
    monkeypatch.setattr(runtime, "_directed_analysis_context_changed", lambda *_args: True)
    monkeypatch.setattr(runtime, "_archive_directed_analysis", lambda *_args: events.append("archive-directed") or 1)
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

    # Registered AI/report reconciliation occurs before the physical AUD close.
    # Since #18, this boundary must remain non-final until the resume finalizer marks
    # the same AUD physically COMPLETED.
    assert recalculate(workspace, AUDIT_ID).processing_status == "PROCESSING"
    # Directed analysis is a final derivation and must not run before the physical
    # AUD close. The post-close handoff is covered separately by #22.
    assert events == [
        "archive-improvement",
        "registered-ai",
        "ai-sealed",
        "data-finalizer",
        "report-validity",
    ]


def test_reprocess_archives_effective_ai_outputs_before_replacement(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    from rasai.audit_fulfillment import start_reprocess_run

    reprocess_id = start_reprocess_run(
        workspace,
        AUDIT_ID,
        source="TEST",
        note="archive derived outputs",
    )
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE improvement_intelligence_runs(
                audit_id TEXT PRIMARY KEY,
                status TEXT
            );
            CREATE TABLE improvement_intelligence_findings(
                finding_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            CREATE TABLE improvement_intelligence_recommendations(
                recommendation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            CREATE TABLE directed_analysis_runs(
                analysis_run_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                input_context_hash TEXT
            );
            CREATE TABLE directed_analysis_actions(
                action_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO improvement_intelligence_runs VALUES (?,?)",
            (AUDIT_ID, "COMPLETE"),
        )
        connection.execute(
            "INSERT INTO improvement_intelligence_findings VALUES (?,?)",
            ("F-1", AUDIT_ID),
        )
        connection.execute(
            "INSERT INTO improvement_intelligence_recommendations VALUES (?,?)",
            ("R-1", AUDIT_ID),
        )
        connection.execute(
            "INSERT INTO directed_analysis_runs VALUES (?,?,?)",
            ("DAN-1", AUDIT_ID, "old-hash"),
        )
        connection.execute(
            "INSERT INTO directed_analysis_actions VALUES (?,?)",
            ("ACT-1", AUDIT_ID),
        )
        connection.commit()
    finally:
        connection.close()

    assert runtime._archive_improvement_intelligence(workspace, AUDIT_ID) == 3
    assert runtime._archive_directed_analysis(workspace, AUDIT_ID) == 2

    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT component,entity_type,entity_id,reprocess_id
               FROM audit_reprocess_derived_archive
               WHERE audit_id=? ORDER BY component,entity_type""",
            (AUDIT_ID,),
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 5
    assert {row[0] for row in rows} == {"IMPROVEMENT_INTELLIGENCE", "DIRECTED_ANALYSIS"}
    assert {row[3] for row in rows} == {reprocess_id}


def test_directed_archive_can_use_explicit_completed_rpr_id(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    from rasai.audit_fulfillment import finish_reprocess_run, start_reprocess_run

    reprocess_id = start_reprocess_run(
        workspace,
        AUDIT_ID,
        source="TEST",
        note="explicit directed archive after inner RPR close",
    )
    finish_reprocess_run(
        workspace,
        reprocess_id,
        status=SUCCESS,
        attempted_items=0,
        successful_items=0,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE directed_analysis_runs(
                analysis_run_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                input_context_hash TEXT
            );
            CREATE TABLE directed_analysis_actions(
                action_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO directed_analysis_runs VALUES (?,?,?)",
            ("DAN-EXPLICIT", AUDIT_ID, "old-hash"),
        )
        connection.execute(
            "INSERT INTO directed_analysis_actions VALUES (?,?)",
            ("ACT-EXPLICIT", AUDIT_ID),
        )
        connection.commit()
    finally:
        connection.close()

    assert runtime._archive_directed_analysis(
        workspace,
        AUDIT_ID,
        reprocess_id=reprocess_id,
    ) == 2

    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            """SELECT reprocess_id,component,entity_id
               FROM audit_reprocess_derived_archive
               WHERE audit_id=? ORDER BY entity_id""",
            (AUDIT_ID,),
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 2
    assert {row[0] for row in rows} == {reprocess_id}
    assert {row[1] for row in rows} == {"DIRECTED_ANALYSIS"}
    assert {row[2] for row in rows} == {"DAN-EXPLICIT", "ACT-EXPLICIT"}


def test_final_directed_refresh_archives_changed_context_under_explicit_rpr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    events: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        runtime,
        "_directed_analysis_context_changed",
        lambda *_args: True,
    )

    def archive(current_workspace, audit_id, *, reprocess_id=None):
        assert current_workspace is workspace
        events.append(("archive", reprocess_id))
        return 2

    monkeypatch.setattr(runtime, "_archive_directed_analysis", archive)

    from rasai import directed_analysis

    expected = SimpleNamespace(status="COMPLETE", reused=False)

    def reprocess(*, audit_id, workspace):
        events.append(("reprocess", audit_id))
        return expected

    monkeypatch.setattr(directed_analysis, "reprocess_directed_analysis", reprocess)

    result = runtime.refresh_final_directed_analysis(
        workspace,
        AUDIT_ID,
        reprocess_id="RPR-CLOSED-BUT-TRACEABLE",
    )

    assert result is expected
    assert events == [
        ("archive", "RPR-CLOSED-BUT-TRACEABLE"),
        ("reprocess", AUDIT_ID),
    ]


def test_final_directed_refresh_reuses_unchanged_context_without_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(
        runtime,
        "_directed_analysis_context_changed",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        runtime,
        "_archive_directed_analysis",
        lambda *_args, **_kwargs: pytest.fail(
            "unchanged directed analysis must not archive effective rows"
        ),
    )

    from rasai import directed_analysis

    expected = SimpleNamespace(status="COMPLETE", reused=True)
    monkeypatch.setattr(
        directed_analysis,
        "reprocess_directed_analysis",
        lambda **_kwargs: expected,
    )

    assert runtime.refresh_final_directed_analysis(
        workspace,
        AUDIT_ID,
        reprocess_id="RPR-UNCHANGED",
    ) is expected


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


def test_semantic_backfill_never_revives_stale_ai_result() -> None:
    from rasai.audit_reprocess import _semantic_backfill_status

    assert _semantic_backfill_status(
        successful_attempt=True,
        assessments=4,
        latest_task_status="STALE",
    ) == FAILED_RETRYABLE
    assert _semantic_backfill_status(
        successful_attempt=True,
        assessments=4,
        latest_task_status="COMPLETE",
    ) == SUCCESS


def test_web_performance_pending_exposes_conditional_ai_dependencies(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_reprocess_final_refinements as final

    monkeypatch.setattr(
        final,
        "_source_forecast_state",
        lambda *_args, **_kwargs: SimpleNamespace(
            improvement_enabled=True,
            directed_ai_enabled=True,
            content_remediation=True,
            technical_remediation=True,
        ),
    )
    pending = (
        SimpleNamespace(
            component="WEB_PERFORMANCE",
            status=FAILED_RETRYABLE,
        ),
    )

    assert final._conditional_ai_dependencies(
        SimpleNamespace(audits_root=str(tmp_path)),
        AUDIT_ID,
        pending,
    ) == (
        "CAT-08 · Análise profunda",
        "Análise Direcionada",
    )


def test_semantic_dependency_ignores_unconsumed_evidence_added_by_web_performance(
    tmp_path: Path,
) -> None:
    from rasai import ai_governance, ai_selective_invalidation

    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            """INSERT INTO evidence(
                evidence_id,audit_id,page_id,snapshot_id,device,evidence_type,source,
                observed_value,artifact_reference,captured_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                "EV-SEM-1",AUDIT_ID,None,"SNP-1","MOBILE","DOM","RENDERED_DOM",
                "conteúdo renderizado",None,"2026-09-19T10:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    first = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        context={"phase":"INITIAL"},
    )
    task_id = ai_governance.register_task(
        workspace=workspace,
        audit_id=AUDIT_ID,
        purpose="SEMANTIC_M7",
        scope_type="SNAPSHOT",
        scope_key="SNP-1",
        evidence_snapshot_id=first.evidence_snapshot_id,
        requirements=("semantic",),
        status=ai_governance.TASK_COMPLETE,
    )
    ai_selective_invalidation.register_task_dependency(
        workspace=workspace,
        ai_task_id=task_id,
        dependency_kind="SNAPSHOT_EVIDENCE",
        scope_key="SNP-1",
    )
    prior_tasks = ai_selective_invalidation._task_state_before_seal(
        workspace,
        AUDIT_ID,
        first.evidence_snapshot_id,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            """INSERT INTO evidence(
                evidence_id,audit_id,page_id,snapshot_id,device,evidence_type,source,
                observed_value,artifact_reference,captured_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                "EV-WEB-1",AUDIT_ID,None,"SNP-1","MOBILE","METRIC","PAGESPEED_INSIGHTS",
                "Lighthouse recuperado",None,"2026-09-19T11:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    second = ai_governance.seal_evidence(
        workspace=workspace,
        audit_id=AUDIT_ID,
        context={"phase":"RPR"},
    )
    ai_selective_invalidation._reconcile_staleness(
        workspace=workspace,
        audit_id=AUDIT_ID,
        prior_snapshot=first,
        new_snapshot=second,
        prior_tasks=prior_tasks,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT status,stale_reason FROM ai_tasks WHERE ai_task_id=?",
            (task_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == ai_governance.TASK_COMPLETE
    assert row[1] is None


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
    ("before", "after", "external_materialized", "expected_external"),
    [
        (
            (("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),),
            (("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),),
            True,
            0,
        ),
        (
            (("CMP-1", "jquery", "3.6.0", "npm", "MEDIUM"),),
            (("CMP-1", "jquery", "3.7.1", "npm", "MEDIUM"),),
            True,
            1,
        ),
        (
            (),
            (),
            False,
            1,
        ),
    ],
)
def test_passive_security_rpr_refreshes_external_intelligence_when_needed(
    monkeypatch,
    tmp_path: Path,
    before,
    after,
    external_materialized: bool,
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
    monkeypatch.setattr(
        runtime,
        "_passive_external_intelligence_materialized",
        lambda *_args: external_materialized,
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


def test_passive_security_deterministic_hook_reuses_selected_governed_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from rasai import passive_security_runtime as passive_runtime
    from rasai import passive_security as security

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        status=SUCCESS,
        result_ref=f"passive_security_runs:{AUDIT_ID}",
        retryable=True,
    )
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """CREATE TABLE passive_security_integrations(
                   audit_id TEXT NOT NULL,
                   integration_id TEXT NOT NULL,
                   state TEXT NOT NULL
               );"""
        )
        connection.executemany(
            "INSERT INTO passive_security_integrations VALUES (?,?,?)",
            (
                (AUDIT_ID, "OSV", "NO_DATA"),
                (AUDIT_ID, "CISA_KEV", "NO_DATA"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setenv(security.ENABLED_ENV, "false")

    with reprocess_policy(
        selected_items=["PASSIVE_SECURITY"],
        use_ai=False,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        result = passive_runtime._deterministic_hook(
            audit_id=AUDIT_ID,
            workspace=workspace,
            source_blocked=False,
        )

    assert result == {
        "status": "COMPLETED",
        "reason": "RPR_GOVERNED_RESULT_REUSED",
    }


def test_passive_security_reconciliation_reopens_success_with_missing_external_coverage(
    tmp_path: Path,
) -> None:
    from rasai import passive_security_runtime as passive_runtime

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
        configuration={"osv": "true", "kev": "true"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        status=SUCCESS,
        result_ref=f"passive_security_runs:{AUDIT_ID}",
        retryable=True,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        before = connection.execute(
            """SELECT last_success_at,effective_result_ref
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='PASSIVE_SECURITY'""",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()

    assert passive_runtime.reconcile_persisted_coverage(workspace, AUDIT_ID) is True

    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == "PASSIVE_SECURITY"
    )
    assert item.status == FAILED_RETRYABLE
    assert item.last_error_code == "PASSIVE_SECURITY_EXTERNAL_COVERAGE_INCOMPLETE"
    assert "CISA_KEV" in str(item.last_error_message)
    assert "OSV" in str(item.last_error_message)

    connection = sqlite3.connect(workspace.database)
    try:
        after = connection.execute(
            """SELECT last_success_at,effective_result_ref
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='PASSIVE_SECURITY'""",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()
    assert after == before


def test_passive_security_reconciliation_keeps_success_when_external_coverage_exists(
    tmp_path: Path,
) -> None:
    from rasai import passive_security_runtime as passive_runtime

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
        configuration={"osv": "true", "kev": "true"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="PASSIVE_SECURITY",
        status=SUCCESS,
        result_ref=f"passive_security_runs:{AUDIT_ID}",
        retryable=True,
    )
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """CREATE TABLE passive_security_integrations(
                   audit_id TEXT NOT NULL,
                   integration_id TEXT NOT NULL,
                   state TEXT NOT NULL
               );"""
        )
        connection.executemany(
            "INSERT INTO passive_security_integrations VALUES (?,?,?)",
            (
                (AUDIT_ID, "OSV", "NO_DATA"),
                (AUDIT_ID, "CISA_KEV", "NO_DATA"),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert passive_runtime.reconcile_persisted_coverage(workspace, AUDIT_ID) is False
    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == "PASSIVE_SECURITY"
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

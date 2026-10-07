from __future__ import annotations

import inspect
from types import SimpleNamespace

from rasai import audit_phase_runtime as phase
from rasai import improvement_reprocess_diagnostics as diagnostics


def test_specific_failure_ignores_generic_not_materialized() -> None:
    specific = SimpleNamespace(
        status="FAILED_RETRYABLE",
        last_error_class="AI_ANALYSIS",
        last_error_code="EVIDENCE_PREPARATION_FAILED",
        last_error_message="evidência inválida",
        retryable=True,
    )
    generic = SimpleNamespace(
        status="FAILED_RETRYABLE",
        last_error_class="ORCHESTRATION",
        last_error_code="IMPROVEMENT_RETRY_NOT_MATERIALIZED",
        last_error_message="genérico",
        retryable=True,
    )

    assert diagnostics._specific_failure(specific) == {
        "status": "FAILED_RETRYABLE",
        "error_class": "AI_ANALYSIS",
        "error_code": "EVIDENCE_PREPARATION_FAILED",
        "error_message": "evidência inválida",
        "retryable": True,
    }
    assert diagnostics._specific_failure(generic) is None


def test_reconciliation_guard_restores_specific_cause(monkeypatch) -> None:
    from rasai import selective_optional_reprocess as optional

    item = SimpleNamespace(
        status="FAILED_RETRYABLE",
        last_error_class="AI_ANALYSIS",
        last_error_code="EVIDENCE_PREPARATION_FAILED",
        last_error_message="causa específica",
        retryable=True,
    )
    saved = optional._reconcile_improvement_rpr

    def generic_reconcile(workspace, audit_id):
        del workspace, audit_id
        item.status = "FAILED_RETRYABLE"
        item.last_error_class = "ORCHESTRATION"
        item.last_error_code = "IMPROVEMENT_RETRY_NOT_MATERIALIZED"
        item.last_error_message = "fallback genérico"
        item.retryable = True

    monkeypatch.setattr(optional, "_reconcile_improvement_rpr", generic_reconcile)
    monkeypatch.setattr(optional, "_item", lambda *args, **kwargs: item)
    monkeypatch.setattr(optional, "_improvement_run", lambda *args, **kwargs: None)

    def project(_workspace, *, audit_id, component, status, error_class, error_code,
                error_message, retryable, **_kwargs):
        assert audit_id == "AUD-1"
        assert component == "IMPROVEMENT_INTELLIGENCE"
        item.status = status
        item.last_error_class = error_class
        item.last_error_code = error_code
        item.last_error_message = error_message
        item.retryable = retryable

    monkeypatch.setattr(diagnostics, "set_work_item_status", project)
    monkeypatch.setattr(diagnostics, "try_append_operational_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(diagnostics, "_improvement_configuration_error", lambda *args, **kwargs: None)
    try:
        diagnostics._install_reconciliation_guard()
        optional._reconcile_improvement_rpr(object(), "AUD-1")
    finally:
        optional._reconcile_improvement_rpr = saved

    assert item.status == "FAILED_RETRYABLE"
    assert item.last_error_class == "AI_ANALYSIS"
    assert item.last_error_code == "EVIDENCE_PREPARATION_FAILED"
    assert item.last_error_message == "causa específica"


def test_governed_hook_guard_projects_escaped_failure(monkeypatch) -> None:
    saved = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    projected: dict[str, object] = {}

    def exploding_hook(*, audit_id, workspace, evidence_snapshot):
        del audit_id, workspace, evidence_snapshot
        raise ValueError("preparação inválida")

    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", exploding_hook, order=300)

    def project(_workspace, *, audit_id, component, status, error_class, error_code,
                error_message, retryable, **_kwargs):
        projected.update(
            audit_id=audit_id,
            component=component,
            status=status,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )

    monkeypatch.setattr(diagnostics, "set_work_item_status", project)
    monkeypatch.setattr(diagnostics, "try_append_operational_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        diagnostics,
        "_improvement_configuration_error",
        lambda *args, **kwargs: None,
    )
    try:
        diagnostics._install_governed_hook_guard()
        outcome = phase._AI_HOOKS["IMPROVEMENT_INTELLIGENCE"].callback(
            audit_id="AUD-1",
            workspace=object(),
            evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
        )
    finally:
        if saved is None:
            phase.unregister_ai_hook("IMPROVEMENT_INTELLIGENCE")
        else:
            phase.register_ai_hook(saved.name, saved.callback, order=saved.order)

    assert outcome == {
        "status": "ERROR",
        "reason": "IMPROVEMENT_GOVERNED_HOOK_VALUEERROR",
    }
    assert projected["status"] == "FAILED_RETRYABLE"
    assert projected["error_class"] == "ORCHESTRATION"
    assert projected["error_code"] == "IMPROVEMENT_GOVERNED_HOOK_VALUEERROR"
    assert "preparação inválida" in str(projected["error_message"])


def test_entrypoints_install_improvement_diagnostics_after_final_binding() -> None:
    import rasai.console_entrypoint as console_entrypoint
    import rasai.entrypoint as entrypoint

    console_source = inspect.getsource(console_entrypoint.main)
    cli_source = inspect.getsource(entrypoint._install_audit_runtime)

    for source in (console_source, cli_source):
        assert source.index("install_final_smoke_closure()") < source.index(
            "install_improvement_reprocess_diagnostics()"
        )
        assert source.index("install_governed_report_projection()") < source.index(
            "install_improvement_reprocess_diagnostics()"
        )
        assert source.index("install_improvement_reprocess_diagnostics()") < source.index(
            "install_audit_resume_runtime()"
        )


def test_registered_ai_dispatch_reports_missing_hook_without_provider(monkeypatch) -> None:
    from rasai import audit_runner
    from rasai import governed_reprocess_runtime as governed

    saved_phase = phase.run_registered_ai_phase
    saved_governed = governed.run_registered_ai_phase
    saved_runner = audit_runner.run_registered_ai_phase
    monkeypatch.setattr(phase, "_AI_HOOKS", {})
    projected: list[tuple[str, str]] = []
    monkeypatch.setattr(
        diagnostics,
        "_project_missing_hook",
        lambda _workspace, audit_id, purpose: projected.append((audit_id, purpose)),
    )
    try:
        diagnostics._install_registered_ai_dispatch_guard()
        outcome = phase.run_registered_ai_phase(
            audit_id="AUD-1",
            workspace=SimpleNamespace(),
            evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
            purposes={"IMPROVEMENT_INTELLIGENCE"},
        )
    finally:
        phase.run_registered_ai_phase = saved_phase
        governed.run_registered_ai_phase = saved_governed
        audit_runner.run_registered_ai_phase = saved_runner

    assert outcome == {
        "IMPROVEMENT_INTELLIGENCE": {
            "status": "SKIPPED",
            "reason": "AI_HOOK_NOT_REGISTERED",
            "provider_called": False,
        }
    }
    assert projected == [("AUD-1", "IMPROVEMENT_INTELLIGENCE")]


def test_registered_ai_dispatch_executes_present_hook_and_diagnoses_missing(
    monkeypatch,
) -> None:
    from rasai import audit_runner
    from rasai import governed_reprocess_runtime as governed

    saved_phase = phase.run_registered_ai_phase
    saved_governed = governed.run_registered_ai_phase
    saved_runner = audit_runner.run_registered_ai_phase
    calls: list[str] = []

    def present(**_kwargs):
        calls.append("PRESENT")
        return {"status": "COMPLETE", "provider": "test"}

    monkeypatch.setattr(
        phase,
        "_AI_HOOKS",
        {"PRESENT": phase._Hook("PRESENT", present, 10)},
    )
    monkeypatch.setattr(
        diagnostics,
        "_project_missing_hook",
        lambda *_args, **_kwargs: None,
    )
    try:
        diagnostics._install_registered_ai_dispatch_guard()
        outcomes = phase.run_registered_ai_phase(
            audit_id="AUD-1",
            workspace=SimpleNamespace(),
            evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
            purposes={"PRESENT", "MISSING"},
        )
    finally:
        phase.run_registered_ai_phase = saved_phase
        governed.run_registered_ai_phase = saved_governed
        audit_runner.run_registered_ai_phase = saved_runner

    assert calls == ["PRESENT"]
    assert outcomes["PRESENT"]["status"] == "COMPLETE"
    assert outcomes["MISSING"] == {
        "status": "SKIPPED",
        "reason": "AI_HOOK_NOT_REGISTERED",
        "provider_called": False,
    }


def test_improvement_configuration_error_is_projected_before_provider(
    monkeypatch,
) -> None:
    saved = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    provider_calls: list[str] = []
    projected: dict[str, object] = {}

    def raw_hook(*, audit_id, workspace, evidence_snapshot):
        del audit_id, workspace, evidence_snapshot
        provider_calls.append("CALLED")
        return {"status": "COMPLETE"}

    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", raw_hook, order=300)
    monkeypatch.setattr(
        diagnostics,
        "_improvement_configuration_error",
        lambda *_args, **_kwargs: "domínios de análise desconhecidos: INVALID",
    )

    def project(_workspace, *, audit_id, component, status, error_class, error_code,
                error_message, retryable, **_kwargs):
        projected.update(
            audit_id=audit_id,
            component=component,
            status=status,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )

    monkeypatch.setattr(diagnostics, "set_work_item_status", project)
    monkeypatch.setattr(
        diagnostics,
        "try_append_operational_event",
        lambda *args, **kwargs: None,
    )
    try:
        diagnostics._install_governed_hook_guard()
        outcome = phase._AI_HOOKS["IMPROVEMENT_INTELLIGENCE"].callback(
            audit_id="AUD-1",
            workspace=SimpleNamespace(),
            evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
        )
    finally:
        if saved is None:
            phase.unregister_ai_hook("IMPROVEMENT_INTELLIGENCE")
        else:
            phase.register_ai_hook(saved.name, saved.callback, order=saved.order)

    assert provider_calls == []
    assert outcome == {
        "status": "NOT_CONFIGURED",
        "reason": "IMPROVEMENT_CONFIGURATION_INVALID",
        "provider_called": False,
    }
    assert projected["status"] == "NOT_CONFIGURED"
    assert projected["error_class"] == "CONFIGURATION"
    assert projected["error_code"] == "IMPROVEMENT_CONFIGURATION_INVALID"
    assert "INVALID" in str(projected["error_message"])


def test_requested_not_executed_optional_item_is_not_counted_as_attempt(
    monkeypatch,
) -> None:
    from rasai import selective_optional_reprocess as optional

    saved = optional._record_optional_attempts
    captured: list[set[str]] = []

    def base(_workspace, _audit_id, components):
        captured.append(set(components))

    monkeypatch.setattr(optional, "_record_optional_attempts", base)

    def item(_workspace, _audit_id, component):
        if component == "IMPROVEMENT_INTELLIGENCE":
            return SimpleNamespace(status="REQUESTED_NOT_EXECUTED")
        return SimpleNamespace(status="FAILED_RETRYABLE")

    monkeypatch.setattr(optional, "_item", item)
    try:
        diagnostics._install_optional_attempt_guard()
        optional._record_optional_attempts(
            SimpleNamespace(),
            "AUD-1",
            {"IMPROVEMENT_INTELLIGENCE", "GOOGLE_SEARCH_CONSOLE"},
        )
    finally:
        optional._record_optional_attempts = saved

    assert captured == [{"GOOGLE_SEARCH_CONSOLE"}]

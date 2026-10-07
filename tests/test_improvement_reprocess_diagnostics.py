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

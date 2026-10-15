"""#138: report materialization cannot recollect external pre-seal evidence.

The collector hook remains the sole acquisition owner. These tests are
in-process, fully mocked and make no provider/network calls.
"""
from __future__ import annotations

from types import SimpleNamespace

from rasai import external_observability_runtime as external
from rasai import governed_optional_runtime as governed
from rasai import report_completion


def _install_captured_hook(monkeypatch, calls):
    hooks = []

    def external_collector(*, audit_id, workspace):
        calls.append(("collect", audit_id, workspace))
        return {"crux-history": {"collection_state": "SUCCESS", "datasets": ["OBS-PRESEAL"]}}

    monkeypatch.setattr(external, "collect_configured_external_observability", external_collector)
    monkeypatch.setattr(
        governed, "register_collection_hook",
        lambda component, handler, *, order: hooks.append((component, handler, order)),
    )
    governed._install_external_observability()
    assert len(hooks) == 1
    component, handler, order = hooks[0]
    assert component == "EXTERNAL_OBSERVABILITY"
    assert order == 50
    return handler


def test_external_observability_is_acquired_once_by_preseal_hook(monkeypatch):
    calls = []
    hook = _install_captured_hook(monkeypatch, calls)
    workspace = object()
    result = hook(audit_id="AUD-FIXTURE", workspace=workspace, source_blocked=False)

    assert result["collection_state"] == "SUCCESS"
    assert result["services"]["crux-history"]["datasets"] == ["OBS-PRESEAL"]
    assert calls == [("collect", "AUD-FIXTURE", workspace)]


def test_finalizer_and_second_materialization_do_not_collect_or_replace_preseal_evidence(monkeypatch):
    calls = []
    hook = _install_captured_hook(monkeypatch, calls)
    workspace = object()
    hook(audit_id="AUD-FIXTURE", workspace=workspace)

    base = SimpleNamespace(
        expected_pages=1, generated_pages=1, missing_pages=(),
        renderer_errors=(),
    )
    def finalizer(*, audit_id, workspace, context_interpretations=(), routing_snapshot=None):
        calls.append(("render", audit_id, workspace))
        return base

    monkeypatch.setattr(report_completion, "_rasai_external_observability_runtime", False, raising=False)
    monkeypatch.setattr(report_completion, "finalize_audit_report_site", finalizer)
    external.install()
    wrapped = report_completion.finalize_audit_report_site

    assert wrapped(audit_id="AUD-FIXTURE", workspace=workspace) is base
    assert wrapped(audit_id="AUD-FIXTURE", workspace=workspace) is base
    assert [c[0] for c in calls] == ["collect", "render", "render"]
    assert getattr(report_completion, "_rasai_external_observability_runtime") is True

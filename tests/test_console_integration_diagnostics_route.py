from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace

from rasai import console_provider_environment as environment
from rasai import console_ui_catalog as catalog
from rasai import integration_diagnostics as diagnostics
from rasai import integration_diagnostics_console as diagnostic_ui


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        audits_root="audits",
        error="",
        operation="LOCAL:MENU",
    )


def _console() -> ModuleType:
    console = ModuleType("test_console_integration_diagnostics_route")
    console.render_header = lambda state: None
    console._save_configuration = lambda state: True
    return console


def _spec(
    integration_id: str,
    label: str,
    *,
    category: str = "Serviços externos",
    safe_for_bulk: bool = True,
) -> diagnostics.IntegrationSpec:
    return diagnostics.IntegrationSpec(
        id=integration_id,
        label=label,
        category=category,
        probe_kind="HTTP",
        dependencies=(),
        probe_cost=diagnostics.PROBE_NO_PROVIDER_FEE,
        safe_for_bulk=safe_for_bulk,
    )


def _result(spec: diagnostics.IntegrationSpec) -> diagnostics.IntegrationDiagnostic:
    return diagnostics.IntegrationDiagnostic(
        integration_id=spec.id,
        label=spec.label,
        checked_at="2026-09-19T12:00:00+00:00",
        status=diagnostics.STATUS_OPERATIONAL,
        category="OK",
        detail="probe concluído",
        action="nenhuma",
        configuration_fingerprint="fixture",
        probe_cost=spec.probe_cost,
    )


def test_integrations_surface_exposes_prominent_canonical_diagnostic_route(monkeypatch) -> None:
    state = _state()
    console = _console()
    calls: list[str] = []

    monkeypatch.setattr(environment, "refresh_specs", lambda: ())
    monkeypatch.setattr(environment.base_environment, "render_header", lambda current: None)
    monkeypatch.setattr(
        diagnostic_ui,
        "integration_menu",
        lambda current_console, current_state, original_environment_menu: calls.append("diagnostic"),
    )
    answers = iter(["D", "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    output = StringIO()
    with redirect_stdout(output):
        catalog.catalog_menu(
            console,
            state,
            view="integrations",
            title="INTEGRAÇÕES E SERVIÇOS",
        )

    rendered = output.getvalue()
    assert "DIAGNÓSTICO / TESTES" in rendered
    assert "D. Diagnóstico / teste de integrações e IA" in rendered
    assert "providers de IA, SERP/Search Intelligence e serviços externos" in rendered
    assert calls == ["diagnostic"]


def test_canonical_diagnostic_menu_exposes_bulk_validation_and_back(monkeypatch) -> None:
    state = _state()
    console = _console()
    monkeypatch.setattr(diagnostics, "integration_specs", lambda: ())
    monkeypatch.setattr(diagnostics, "load_diagnostics", lambda audits_root: {})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "V")

    output = StringIO()
    with redirect_stdout(output):
        diagnostic_ui.integration_menu(console, state, lambda current: None)

    rendered = output.getvalue()
    assert "Inclui providers de IA, SERP/Search Intelligence e serviços externos configurados." in rendered
    assert "T. Validar integrações e IAs configuradas — somente probes seguros" in rendered
    assert "V. Voltar" in rendered


def test_bulk_validation_keeps_safe_for_bulk_policy(monkeypatch) -> None:
    state = _state()
    console = _console()
    safe = _spec("service:safe", "Serviço seguro")
    scarce = _spec("service:scarce", "Serviço quota escassa", safe_for_bulk=False)
    executed: list[str] = []

    monkeypatch.setattr(
        diagnostic_ui,
        "_run_and_store",
        lambda current_state, spec: executed.append(spec.id) or _result(spec),
    )
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")

    output = StringIO()
    with redirect_stdout(output):
        diagnostic_ui._bulk_validate(console, state, (safe, scarce))

    rendered = output.getvalue()
    assert executed == ["service:safe"]
    assert "Serviço quota escassa: omitida no lote" in rendered
    assert "permanece" in rendered or "individual" in rendered


def test_individual_integration_can_be_retested_and_returned(monkeypatch) -> None:
    state = _state()
    console = _console()
    spec = _spec("ai:test", "IA de teste", category="IA")
    executed: list[str] = []

    monkeypatch.setattr(diagnostics, "load_diagnostics", lambda audits_root: {})
    monkeypatch.setattr(
        diagnostic_ui,
        "_run_and_store",
        lambda current_state, current_spec: executed.append(current_spec.id) or _result(current_spec),
    )
    answers = iter(["T", "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    output = StringIO()
    with redirect_stdout(output):
        diagnostic_ui._detail_menu(console, state, spec)

    rendered = output.getvalue()
    assert "T. Validar / retestar integração" in rendered
    assert "V. Voltar" in rendered
    assert executed == ["ai:test"]

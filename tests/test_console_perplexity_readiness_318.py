"""#318: console readiness distinguishes integration configuration from AUD intent."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace

from rasai.console_perplexity_readiness_318 import (
    inspect_perplexity_readiness,
    render_perplexity_readiness,
)
from rasai import integration_diagnostics_console as ui
from rasai.integration_diagnostics import get_integration_spec


def _state(**kwargs):
    defaults = {
        "audits_root": "audits", "operation": "", "error": "",
        "perplexity_queries": (), "perplexity_search_type": "web",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_key_and_enabled_are_not_billable_request() -> None:
    state = _state(search_queries=("seguro de vida",))
    before = vars(state).copy()
    info = inspect_perplexity_readiness(state, environment={
        "PERPLEXITY_API_KEY": "opaque-test-secret",
        "RASAI_PERPLEXITY_ENABLED": "true",
        "RASAI_PERPLEXITY_MAX_RESULTS": "10",
    })
    assert info["enabled"] is True
    assert info["credential_configured"] is True
    assert info["queries_requested"] is False
    assert info["executable_request_pending"] is False
    assert info["status"] == "NÃO SOLICITADA - DEFINIR QUERIES NO CAT-05"
    assert vars(state) == before
    assert "opaque-test-secret" not in str(info)


def test_configured_filters_are_optional_and_not_per_aud_request() -> None:
    info = inspect_perplexity_readiness(_state(), environment={
        "PERPLEXITY_API_KEY": "fixture",
        "RASAI_PERPLEXITY_ENABLED": "true",
        "RASAI_PERPLEXITY_COUNTRY": "BR",
        "RASAI_PERPLEXITY_SEARCH_LANGUAGE_FILTER": "pt",
    })
    assert info["optional_filters_configured"] == 2
    assert not info["executable_request_pending"]


def test_queries_are_explicit_and_never_inferred_from_serp() -> None:
    state = _state(perplexity_queries=("seguro de vida",),
                   search_queries=("seguro de vida", "seguro de carro"),
                   perplexity_search_type="fast")
    info = inspect_perplexity_readiness(state, environment={
        "PERPLEXITY_API_KEY": "fixture", "RASAI_PERPLEXITY_ENABLED": "true",
    })
    assert info["executable_request_pending"] is True
    assert info["query_count"] == 1
    assert info["mode"] == "FAST"
    assert "CONFIRMAÇÃO" in info["status"]


def test_disabled_and_missing_key_never_ready_even_with_queries() -> None:
    s = _state(perplexity_queries=("seguro de vida",))
    disabled = inspect_perplexity_readiness(s, environment={
        "PERPLEXITY_API_KEY": "fixture", "RASAI_PERPLEXITY_ENABLED": "false",
    })
    missing = inspect_perplexity_readiness(s, environment={
        "RASAI_PERPLEXITY_ENABLED": "true",
    })
    assert disabled["enabled"] is False
    assert disabled["executable_request_pending"] is False
    assert missing["credential_configured"] is False
    assert missing["executable_request_pending"] is False


def test_render_has_explicit_operator_instruction_but_no_secret(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "private-fixture-do-not-display")
    monkeypatch.setenv("RASAI_PERPLEXITY_ENABLED", "true")
    output = StringIO()
    state = _state()
    with redirect_stdout(output):
        render_perplexity_readiness(state)
    result = output.getvalue()
    assert "NÃO SOLICITADA" in result
    assert "CAT-05" in result and "queries" in result.lower()
    assert "Filtros adicionais" in result and "opcionais" in result
    assert "private-fixture-do-not-display" not in result


def test_integration_detail_offers_direct_opt_in_route_without_provider_call(monkeypatch):
    from rasai import console_search_parameter_menu as submenu
    spec = get_integration_spec("search:perplexity")
    assert spec is not None
    events = []
    monkeypatch.setattr(submenu, "_configure_perplexity",
                        lambda _module, state: events.append("configure"))
    monkeypatch.setattr(ui, "_render_dependencies", lambda _state, _spec: None)
    monkeypatch.setattr(ui, "_render_result", lambda _spec, _result: None)
    monkeypatch.setattr(ui.diagnostics, "load_diagnostics", lambda _root: {})
    responses = iter(("P", "V"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    module = ModuleType("console_test")
    module.render_header = lambda _state: None
    output = StringIO()
    with redirect_stdout(output):
        ui._detail_menu(module, _state(), spec)
    assert events == ["configure"]
    assert "Configurar pesquisa Perplexity nesta AUD" in output.getvalue()


def test_perplexity_dependency_editor_has_request_route_separate_from_key(monkeypatch):
    from rasai import console_search_parameter_menu as submenu
    spec = get_integration_spec("search:perplexity")
    assert spec is not None
    events = []
    monkeypatch.setattr(submenu, "_configure_perplexity",
                        lambda _module, state: events.append("configure"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "P")
    module = ModuleType("console_test")
    module.render_header = lambda _state: None
    output = StringIO()
    with redirect_stdout(output):
        result = ui._edit_dependency(module, _state(), spec)
    assert result is False
    assert events == ["configure"]
    assert "PARA ESTA AUD" in output.getvalue()

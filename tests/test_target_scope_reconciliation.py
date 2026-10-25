"""Focused no-network checks for the single-URL consumer scope contract."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai.target_scope_reconciliation import (
    bind, canonical_target, consumer_status, execution_matrix,
    must_review, notices, scope_preflight, scope_state,
)


def test_changed_origin_preserves_queries_and_requires_operator_review():
    state = SimpleNamespace(
        target="https://insurance.example/vida", search_queries=("seguro de vida",),
        perplexity_queries=(), perplexity_draft_queries=("seguro de vida",),
        search_scope_target="", perplexity_scope_target="",
    )
    bind(state, "SERP")
    bind(state, "PERPLEXITY")
    state.target = "https://www.nytimes.com/"
    assert consumer_status(state, "SERP") == "ORIGIN_CHANGED"
    assert consumer_status(state, "PERPLEXITY") == "ORIGIN_CHANGED"
    assert must_review(state)
    assert len(notices(state)) == 2
    assert state.search_queries == ("seguro de vida",)
    assert state.perplexity_draft_queries == ("seguro de vida",)
    bind(state, "SERP")
    bind(state, "PERPLEXITY")
    assert consumer_status(state, "SERP") == "SAME_TARGET"
    assert not must_review(state)


def test_path_change_and_old_ini_without_binding_are_not_false_proof():
    old = "HTTPS://EXAMPLE.ORG/a#part"
    assert canonical_target(old) == "https://example.org/a"
    assert scope_state("https://example.org/b", old, requested=True) == "PATH_CHANGED"
    assert scope_state("https://example.org/b", "", requested=True) == "SOURCE_UNVERIFIED"
    assert scope_state("https://example.org/b", old, requested=False) == "NOT_REQUESTED"
    assert scope_state("", old, requested=True) == "TARGET_INVALID"


def test_preflight_rejects_cross_aud_target_without_network():
    scope_preflight("https://example.org/product#section", "https://example.org/product")
    with pytest.raises(ValueError, match="TARGET_SCOPE_MISMATCH"):
        scope_preflight("https://example.org/product", "https://another.example/")


def test_matrix_inherits_target_and_isolates_gsc_property():
    state = SimpleNamespace(
        target="https://www.nytimes.com/",
        search_queries=("travel",), search_scope_target="",
        perplexity_queries=(), perplexity_draft_queries=(), perplexity_scope_target="",
    )
    rows = execution_matrix(state, {
        "RASAI_GSC_ENABLED": "true",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "sc-domain:another.example",
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "not-a-real-token",
    })
    assert rows[0][1] == "HERDADA"
    assert rows[0][2] == "https://www.nytimes.com/"
    assert rows[1][2] == "SOURCE_UNVERIFIED"
    assert rows[3][2] == "PROPERTY_URL_MISMATCH"


def test_ini_search_and_perplexity_provenance_roundtrip_without_paid_calls():
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai import console_settings

    _install_search_persistence()
    state = SearchConsoleState(target="https://www.nytimes.com/")
    state.search_queries = ("travel",)
    state.perplexity_draft_queries = ("travel",)
    bind(state, "SERP")
    bind(state, "PERPLEXITY")
    saved = console_settings._state_values(state)
    assert saved["search_intelligence"]["source_target"] == "https://www.nytimes.com/"
    assert saved["perplexity_draft"]["source_target"] == "https://www.nytimes.com/"

    restored = SearchConsoleState(target="https://example.org/")
    for section in ("search_intelligence", "perplexity_draft"):
        for key, value in saved[section].items():
            console_settings._assign(restored, section, key, value)
    assert consumer_status(restored, "SERP") == "ORIGIN_CHANGED"
    assert consumer_status(restored, "PERPLEXITY") == "ORIGIN_CHANGED"

    legacy = SearchConsoleState(target="https://example.org/")
    console_settings._assign(legacy, "search_intelligence", "queries", "travel")
    assert consumer_status(legacy, "SERP") == "SOURCE_UNVERIFIED"


def test_rejecting_stale_search_temporarily_excludes_cat05_without_changing_plan(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from types import ModuleType
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_catalog_plan import selected_catalog_ids, set_selected_catalog_ids, _PLANS
    from rasai.console_perplexity_run_gate import install

    state = SearchConsoleState(target="https://new.example/")
    state.search_queries = ("old brand",)
    state.search_scope_target = "https://old.example/"
    state.perplexity_draft_queries = ("old brand",)
    state.perplexity_scope_target = "https://old.example/"
    _PLANS.clear()
    try:
        set_selected_catalog_ids(state, ["CAT-01", "CAT-05"])
        called = []
        module = ModuleType("target_scope_test_console")
        def run(current):
            called.append((selected_catalog_ids(current), current.search_queries,
                           current.perplexity_queries))
            return 0
        module.run_audit_from_console = run
        install(module)
        monkeypatch.setattr("builtins.input", lambda prompt="": "N")
        with redirect_stdout(StringIO()):
            assert module.run_audit_from_console(state) == 0
        assert called == [(("CAT-01",), (), ())]
        assert selected_catalog_ids(state) == ("CAT-01", "CAT-05")
        assert state.search_queries == ("old brand",)
    finally:
        _PLANS.clear()


def test_explicit_source_urls_are_visible_even_if_url_editor_normalizes_trailing_slash():
    from rasai.target_scope_reconciliation import bound_url_label, scope_display_rows
    from rasai.console_search_intelligence import SearchConsoleState

    state = SearchConsoleState(target="https://www.nytimes.com/")
    state.search_queries = ("seguro de vida",)
    state.search_scope_target = "https://seguros.example/vida"
    state.perplexity_draft_queries = ("seguro para família",)
    state.perplexity_scope_target = "https://seguros.example/vida"
    assert scope_display_rows(state, "SERP") == (
        ("URL da auditoria", "https://www.nytimes.com/"),
        ("URL vinculada aos termos", "https://seguros.example/vida"),
        ("Situação do vínculo", "ORIGIN_CHANGED"),
    )
    assert bound_url_label(state, "PERPLEXITY") == "https://seguros.example/vida"
    for notice in notices(state):
        assert "https://seguros.example/vida" in notice
        assert "https://www.nytimes.com/" in notice
    assert canonical_target("https://www.nytimes.com") == canonical_target(state.target)

    state.search_scope_target = ""
    assert bound_url_label(state, "SERP") == "<URL anterior não registrada no INI>"
    state.search_queries = ()
    assert bound_url_label(state, "SERP") == "<sem consultas configuradas>"


def test_changed_url_editor_shows_existing_origin_without_claiming_slash_change(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from rasai import interactive_console
    from rasai.console_search_intelligence import SearchConsoleState

    state = SearchConsoleState(
        target="https://www.nytimes.com/", search_queries=("seguro de vida",),
        search_scope_target="https://seguros.example/vida",
    )
    monkeypatch.setattr(interactive_console, "render_header", lambda state: None)
    monkeypatch.setattr(interactive_console, "prompt_text", lambda *a, **k: "https://www.nytimes.com")
    output = StringIO()
    with redirect_stdout(output):
        interactive_console._configure(state, "1")
    view = output.getvalue()
    assert "URL normalizada não mudou" in view
    assert "https://seguros.example/vida" in view
    assert state.target == "https://www.nytimes.com/"
    assert state.search_queries == ("seguro de vida",)


def test_cat05_editor_and_summary_print_both_source_urls_without_network(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from unittest.mock import patch
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_search_parameter_menu import _render_execution_menu, _configure_perplexity
    from rasai.search_intelligence.config import SerpRuntimeConfig
    from rasai import console_search_intelligence

    state = SearchConsoleState(target="https://www.nytimes.com/")
    state.search_queries = ("seguro de vida",)
    state.search_scope_target = "https://seguros.example/vida"
    state.perplexity_draft_queries = ("seguro para família",)
    state.perplexity_scope_target = "https://seguro.example/familia"
    output = StringIO()
    with redirect_stdout(output):
        _render_execution_menu(state, SerpRuntimeConfig.from_environment())
    rendered = output.getvalue()
    assert "https://www.nytimes.com/" in rendered
    assert "https://seguros.example/vida" in rendered
    assert "https://seguro.example/familia" in rendered

    output = StringIO()
    with patch("builtins.input", return_value="V"), redirect_stdout(output):
        _configure_perplexity(console_search_intelligence, state)
    assert "https://seguro.example/familia" in output.getvalue()
    assert "https://www.nytimes.com/" in output.getvalue()
    assert state.perplexity_queries == ()


def test_matrix_includes_actual_configured_gsc_property_without_touching_credentials():
    from rasai.console_search_intelligence import SearchConsoleState

    state = SearchConsoleState(target="https://www.nytimes.com/")
    state.search_queries = ("travel",)
    state.search_scope_target = "https://another.example/"
    state.perplexity_draft_queries = ("travel",)
    state.perplexity_scope_target = "https://different.example/"
    rows = execution_matrix(state, {
        "RASAI_GSC_ENABLED": "true",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "sc-domain:another.example",
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "SECRET_DO_NOT_EXPOSE",
    })
    assert rows[3][2] == "PROPERTY_URL_MISMATCH"
    assert rows[4][2] == "https://another.example/"
    assert rows[5][2] == "https://different.example/"
    assert rows[6][2] == "sc-domain:another.example"
    assert "SECRET_DO_NOT_EXPOSE" not in str(rows)


def test_changing_target_propagates_derived_state_but_preserves_independent_sources():
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.target_scope_reconciliation import propagate_target, related_scope_summary

    state = SearchConsoleState(target="https://insurance.example/vida")
    state.current_url = state.target
    state.search_queries = ("seguro de vida",)
    state.search_scope_target = "https://insurance.example/vida"
    state.perplexity_draft_queries = ("seguro familiar",)
    state.perplexity_scope_target = "https://insurance.example/vida"

    assert propagate_target(state, "https://www.nytimes.com")
    assert state.target == "https://www.nytimes.com/"
    assert state.current_url == state.target
    assert state.search_scope_target == "https://insurance.example/vida"
    assert state.perplexity_scope_target == "https://insurance.example/vida"
    assert state.search_queries == ("seguro de vida",)
    assert state.perplexity_draft_queries == ("seguro familiar",)
    lines = related_scope_summary(state, environment={
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "sc-domain:insurance.example",
        "RASAI_GSC_ENABLED": "false",
    })
    assert any("CATs técnicos/Apdex/IA" in line for line in lines)
    assert any("23579716" in line for line in lines)
    assert any("CAT-05 > 1 > P" in line for line in lines)
    assert not propagate_target(state, "https://www.nytimes.com/")
    assert state.target == "https://www.nytimes.com/"


def test_target_change_rebinds_only_uncharged_inert_query_context():
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.target_scope_reconciliation import propagate_target
    state = SearchConsoleState(target="https://old.example/", search_scope_target="https://old.example/")
    state.perplexity_scope_target = "https://old.example/"
    assert propagate_target(state, "https://new.example")
    assert state.search_scope_target == "https://new.example/"
    assert state.perplexity_scope_target == "https://new.example/"
    assert state.search_queries == ()
    assert state.perplexity_draft_queries == ()


def test_target_roundtrip_canonicalizes_ini_without_inventing_query_provenance(tmp_path):
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai import console_settings
    _install_search_persistence()
    state = SearchConsoleState()
    console_settings._assign(state, "console", "target", "https://www.nytimes.com")
    assert state.target == state.current_url == "https://www.nytimes.com/"
    console_settings._assign(state, "search_intelligence", "queries", "seguro de vida")
    assert consumer_status(state, "SERP") == "SOURCE_UNVERIFIED"
    path = tmp_path / "rasai-console.ini"
    console_settings.save_console_config(state, path)
    restored = SearchConsoleState()
    console_settings.load_console_config(restored, path)
    assert restored.target == restored.current_url == "https://www.nytimes.com/"
    assert consumer_status(restored, "SERP") == "SOURCE_UNVERIFIED"


def test_dependency_assistant_routes_to_existing_editors_without_network(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from types import ModuleType
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_target_dependency_guide import review_target_dependencies
    from rasai import console_search_parameter_menu as menu
    from rasai import console_ui_catalog

    state = SearchConsoleState(target="https://www.nytimes.com/")
    calls = []
    monkeypatch.setattr(menu, "configure_search_parameters", lambda module, state: calls.append("serp"))
    monkeypatch.setattr(menu, "_configure_perplexity", lambda module, state: calls.append("perplexity"))
    monkeypatch.setattr(console_ui_catalog, "variable_editor", lambda module, state, spec: calls.append(spec.name))
    answers = iter(["1", "2", "3", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    with redirect_stdout(StringIO()):
        review_target_dependencies(ModuleType("console"), state)
    assert calls == ["serp", "perplexity", "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"]


def test_legacy_noop_slash_does_not_trigger_extra_save(monkeypatch):
    from rasai import interactive_console
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.target_scope_reconciliation import propagate_target
    state = SearchConsoleState(target="https://www.nytimes.com/")
    monkeypatch.setattr(interactive_console, "render_header", lambda state: None)
    monkeypatch.setattr(interactive_console, "prompt_text", lambda *a, **k: "https://www.nytimes.com")
    interactive_console._configure(state, "1")
    assert state.target == "https://www.nytimes.com/"


def test_url_change_can_open_guided_edit_before_one_ini_save(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from types import ModuleType
    from rasai import console_ui_refactor as ui
    from rasai import console_target_dependency_guide as assistant
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.target_scope_reconciliation import propagate_target

    console = ModuleType("target_session_config")
    state = SearchConsoleState(target="https://old.example/")
    calls = []
    console._configure = lambda current, choice: propagate_target(current, "https://new.example/")
    console.mark_dirty = lambda current, value=True: None
    console._save_configuration = lambda current: calls.append(
        ("save", current.target, current.current_url)
    ) or True
    monkeypatch.setattr(
        assistant, "review_target_dependencies",
        lambda module, current: calls.append(("guided", current.target)),
    )
    answer = iter(("A", "2"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answer))
    ui._install_configure_persistence(console)
    with redirect_stdout(StringIO()) as stdout:
        console._configure(state, "1")
    assert calls == [
        ("guided", "https://new.example/"),
        ("save", "https://new.example/", "https://new.example/"),
    ]
    assert "A. Ajustar agora" in stdout.getvalue()


def test_url_scope_normalization_does_not_prompt_save_for_same_target(monkeypatch):
    from contextlib import redirect_stdout
    from io import StringIO
    from types import ModuleType
    from rasai import console_ui_refactor as ui
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.target_scope_reconciliation import propagate_target

    console = ModuleType("same_target_noop")
    state = SearchConsoleState(target="https://www.nytimes.com/")
    console._configure = lambda current, choice: propagate_target(current, "https://www.nytimes.com")
    console.mark_dirty = lambda current, value=True: None
    console._save_configuration = lambda current: pytest.fail("unexpected INI write")
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": pytest.fail("unchanged URL should not prompt persistence"),
    )
    ui._install_configure_persistence(console)
    with redirect_stdout(StringIO()):
        console._configure(state, "1")
    assert state.target == state.current_url == "https://www.nytimes.com/"

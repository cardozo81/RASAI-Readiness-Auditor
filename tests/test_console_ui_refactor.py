from __future__ import annotations

import builtins
from configparser import ConfigParser
from contextlib import redirect_stdout
from io import StringIO
import os
from types import ModuleType, SimpleNamespace

import pytest

from rasai.console_m23 import State as ApdexConsoleState
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_settings
from rasai import console_ui_refactor as ui


@pytest.fixture(autouse=True)
def _isolate_console_ui_process_state():
    environment = dict(os.environ)
    ui._SESSION_META.clear()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environment)
        ui._SESSION_META.clear()


def test_configuration_ids_are_numeric_stable_and_unique_for_current_catalog() -> None:
    from rasai import console_provider_environment as environment

    specs = environment.refresh_specs()
    ids = [ui.configuration_id(spec.name) for spec in specs]
    assert ids
    assert all(value.isdigit() and len(value) == 8 for value in ids)
    assert len(ids) == len(set(ids))
    for spec in specs:
        assert ui.configuration_id(spec.name) == ui.configuration_id(spec.name)


def test_device_drives_normal_experience_mix_without_tablet() -> None:
    assert ui._derived_apdex_mix("mobile") == "mobile=100,desktop=0,tablet=0"
    assert ui._derived_apdex_mix("desktop") == "mobile=0,desktop=100,tablet=0"
    assert ui._derived_apdex_mix("both") == "mobile=60,desktop=40,tablet=0"


def test_device_drives_mobile_and_desktop_result_visibility() -> None:
    assert ui._device_result_states(SimpleNamespace(device="mobile")) == ("INCLUÍDO", "NÃO APLICÁVEL")
    assert ui._device_result_states(SimpleNamespace(device="desktop")) == ("NÃO APLICÁVEL", "INCLUÍDO")
    assert ui._device_result_states(SimpleNamespace(device="both")) == ("INCLUÍDO", "INCLUÍDO")


def test_search_capability_filter_does_not_expose_unrelated_ai_variables() -> None:
    specs = ui._capability_specs("search-intelligence")
    names = {spec.name for spec in specs}
    assert any("SERP" in name or "SEARCH_CONSOLE" in name or "GSC_" in name for name in names)
    assert "OPENAI_API_KEY" not in names
    assert "RASAI_CRUX_API_KEY" not in names


def test_search_console_notice_matches_explicit_save_contract() -> None:
    rendered = ui._rewrite_search_copy(ui._SEARCH_OLD_NOTICE)
    assert "não são gravados" not in rendered
    assert "Salvar configuração" in rendered
    assert "rasai-console.ini" in rendered


def test_search_inputs_are_persisted_only_by_console_save(tmp_path) -> None:
    ui._install_search_persistence()
    state = SearchConsoleState()
    state.search_queries = ("seguro residencial", "seguro casa")
    state.search_depth = 17
    state.search_region = "Porto Alegre, RS, Brazil"
    state.search_device = "desktop"
    state.search_competitive = False
    state.search_compare_content = True
    state.search_max_content_pages = 4
    state.search_content_timeout_seconds = 12.5
    state.search_content_max_bytes = 1_500_000
    state.search_content_max_redirects = 2
    state.search_ai_competitive = True
    state.search_ymyl_mode = "ON"
    destination = tmp_path / "rasai-console.ini"

    console_settings.save_console_config(state, destination)
    parser = ConfigParser(interpolation=None)
    parser.read(destination, encoding="utf-8")
    assert parser.get("search_intelligence", "queries") == "seguro residencial; seguro casa"
    assert parser.getint("search_intelligence", "depth") == 17
    assert parser.get("search_intelligence", "device") == "desktop"
    assert parser.getboolean("search_intelligence", "competitive") is False
    assert parser.getboolean("search_intelligence", "compare_content") is True
    assert parser.getint("search_intelligence", "max_content_pages") == 4
    assert parser.getfloat("search_intelligence", "content_timeout_seconds") == 12.5
    assert parser.getint("search_intelligence", "content_max_bytes") == 1_500_000
    assert parser.getint("search_intelligence", "content_max_redirects") == 2
    assert parser.getboolean("search_intelligence", "ai_competitive") is True
    assert parser.get("search_intelligence", "ymyl_mode") == "ON"

    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)
    assert restored.search_queries == state.search_queries
    assert restored.search_depth == 17
    assert restored.search_region == state.search_region
    assert restored.search_device == state.search_device
    assert restored.search_competitive is False
    assert restored.search_compare_content is True
    assert restored.search_max_content_pages == 4
    assert restored.search_content_timeout_seconds == 12.5
    assert restored.search_content_max_bytes == 1_500_000
    assert restored.search_content_max_redirects == 2
    assert restored.search_ai_competitive is True
    assert restored.search_ymyl_mode == "ON"


def test_inherited_experience_mix_is_not_materialized_as_override(tmp_path) -> None:
    ui._install_search_persistence()
    state = ApdexConsoleState(device="both")
    state.apdex_experience_device_mix = ui._derived_apdex_mix("both")
    ui._set_mix_inherited(state, True)
    destination = tmp_path / "rasai-console.ini"

    console_settings.save_console_config(state, destination)
    parser = ConfigParser(interpolation=None)
    parser.read(destination, encoding="utf-8")
    assert not parser.has_option("synthetic_apdex_experience", "device_mix")


def test_apdex_edit_keeps_mix_inherited_when_mix_is_unchanged(monkeypatch) -> None:
    console = ModuleType("test_console_ui_refactor_apdex_inherited")
    console._configure = lambda state, choice: setattr(
        state, "apdex_experience_samples", state.apdex_experience_samples + 1
    )
    console.mark_dirty = lambda state, value=True: None
    console._save_configuration = lambda state: True
    state = ApdexConsoleState(device="both")
    state.apdex_experience = True
    state.apdex_experience_device_mix = ui._derived_apdex_mix("both")
    ui._set_mix_inherited(state, True)

    ui._install_configure_persistence(console)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "1")
    console._configure(state, "11")

    assert ui._mix_inherited(state) is True
    assert state.apdex_experience_device_mix == "mobile=60,desktop=40,tablet=0"


def test_apdex_edit_marks_mix_override_only_when_mix_changes(monkeypatch) -> None:
    console = ModuleType("test_console_ui_refactor_apdex_override")

    def change_mix(state, choice):
        state.apdex_experience_device_mix = "mobile=50,desktop=50,tablet=0"

    console._configure = change_mix
    console.mark_dirty = lambda state, value=True: None
    console._save_configuration = lambda state: True
    state = ApdexConsoleState(device="both")
    state.apdex_experience = True
    state.apdex_experience_device_mix = ui._derived_apdex_mix("both")
    ui._set_mix_inherited(state, True)

    ui._install_configure_persistence(console)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "1")
    console._configure(state, "11")

    assert ui._mix_inherited(state) is False
    assert state.apdex_experience_device_mix == "mobile=50,desktop=50,tablet=0"


def test_preparation_surface_is_catalog_driven_and_returns_home(monkeypatch) -> None:
    console = ModuleType("test_console_ui_refactor_preparation")
    console.render_header = lambda state: None
    console._execution_readiness = lambda state: (True, "configuração válida")
    console._configure = lambda state, choice: None
    state = SearchConsoleState(target="https://example.com/")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "V")

    output = StringIO()
    with redirect_stdout(output):
        assert ui._preparation_menu(console, state, lambda current: "") == "V"
    rendered = output.getvalue()
    assert "CATÁLOGO DA AUDITORIA" in rendered
    assert "PLANO DA PRÓXIMA AUDITORIA" in rendered
    assert "CAT-01" in rendered
    assert "CAT-09" in rendered
    assert "PERFIL DA PRÓXIMA AUDITORIA" not in rendered
    assert "ANÁLISES / RESULTADOS" not in rendered


def test_top_level_canonical_navigation_is_not_stdout_buffered() -> None:
    import rasai.console_navigation as navigation

    console = ModuleType("test_console_ui_refactor_live_stdout")
    console.render_header = lambda state: None
    console._menu = lambda state: "Q"
    navigation.install(console)
    canonical_menu = console._menu

    ui._install_top_level_menu(console)

    assert console._menu is canonical_menu
    assert console._rasai_top_level_information_architecture is True
    assert console._rasai_top_level_live_stdout_passthrough is True


def test_top_level_information_architecture_keeps_canonical_navigation_owner(monkeypatch) -> None:
    import rasai.console_navigation as navigation
    from rasai import console_ui_catalog

    console = ModuleType("test_console_ui_refactor_top")
    console.render_header = lambda state: None
    console._menu = lambda state: builtins.input("Escolha: ").strip().upper()
    navigation.install(console)
    ui._install_top_level_menu(console)
    state = SimpleNamespace(project="Projeto", target="https://example.com/", audit_id="", audits_root="audits", error="")

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        console_ui_catalog,
        "catalog_menu",
        lambda current_console, current_state, *, view, title: calls.append((view, title)),
    )
    answers = iter(["4", "Q"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    output = StringIO()
    with redirect_stdout(output):
        assert console._menu(state) == "Q"
    rendered = output.getvalue()
    assert "4. Inteligência Artificial" in rendered
    assert "5. Integrações e serviços" in rendered
    assert "6. Todas as configurações" in rendered
    assert "7. Sistema / restaurar padrões" in rendered
    assert calls == [("ai", "INTELIGÊNCIA ARTIFICIAL")]


def test_top_level_integrations_reaches_final_integrations_router(monkeypatch) -> None:
    import rasai.console_navigation as navigation
    from rasai import integration_diagnostics_console as diagnostics_console

    console = ModuleType("test_console_ui_refactor_integrations_route")
    console.render_header = lambda state: None
    console._menu = lambda state: builtins.input("Escolha: ").strip().upper()
    navigation.install(console)
    ui._install_top_level_menu(console)
    state = SimpleNamespace(project="Projeto", target="https://example.com/", audit_id="", audits_root="audits", error="")

    monkeypatch.setattr(builtins, "input", lambda prompt="": "5")
    assert console._menu(state) == "E"
    assert ui._config_view(state) == "integrations"

    calls: list[str] = []
    monkeypatch.setattr(
        diagnostics_console,
        "integration_menu",
        lambda current_console, current_state, open_all: calls.append("diagnostics"),
    )
    ui._install_environment_router(console)
    console._environment_menu(state)

    assert calls == ["diagnostics"]


def test_integrations_router_keeps_all_configuration_callback(monkeypatch) -> None:
    from rasai import integration_diagnostics_console as diagnostics_console

    console = ModuleType("test_console_ui_refactor_integrations_config")
    state = SimpleNamespace(project="Projeto", target="https://example.com/", audit_id="", audits_root="audits", error="")
    ui._set_config_view(state, "integrations")
    calls: list[tuple[str, str]] = []

    def open_diagnostics(current_console, current_state, open_all):
        calls.append(("diagnostics", "open"))
        open_all(current_state)

    monkeypatch.setattr(diagnostics_console, "integration_menu", open_diagnostics)
    monkeypatch.setattr(
        ui,
        "catalog_menu",
        lambda current_console, current_state, *, view, title: calls.append((view, title)),
    )

    ui._install_environment_router(console)
    console._environment_menu(state)

    assert calls == [
        ("diagnostics", "open"),
        ("all", "TODAS AS CONFIGURAÇÕES"),
    ]


def test_post_edit_persistence_offers_session_or_immediate_save(monkeypatch) -> None:
    console = ModuleType("test_console_ui_refactor_persist")
    console._configure = lambda state, choice: setattr(state, "project", "Alterado")
    console.mark_dirty = lambda state, value=True: setattr(state, "config_dirty", value)
    saves: list[str] = []
    console._save_configuration = lambda state: saves.append(state.project) or True
    state = SearchConsoleState(project="Original")

    ui._install_configure_persistence(console)
    answers = iter(["2"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    console._configure(state, "2")
    assert state.project == "Alterado"
    assert saves == ["Alterado"]

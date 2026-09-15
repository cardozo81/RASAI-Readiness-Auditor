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


def test_search_capability_filter_does_not_expose_unrelated_ai_variables() -> None:
    specs = ui._capability_specs("search-intelligence")
    names = {spec.name for spec in specs}
    assert any("SERP" in name or "SEARCH_CONSOLE" in name or "GSC_" in name for name in names)
    assert "OPENAI_API_KEY" not in names
    assert "RASAI_CRUX_API_KEY" not in names


def test_search_inputs_are_persisted_only_by_console_save(tmp_path) -> None:
    ui._install_search_persistence()
    state = SearchConsoleState()
    state.search_queries = ("seguro residencial", "seguro casa")
    state.search_depth = 17
    state.search_region = "Porto Alegre, RS, Brazil"
    state.search_device = "desktop"
    state.search_competitive = False
    destination = tmp_path / "rasai-console.ini"

    console_settings.save_console_config(state, destination)
    parser = ConfigParser(interpolation=None)
    parser.read(destination, encoding="utf-8")
    assert parser.get("search_intelligence", "queries") == "seguro residencial; seguro casa"
    assert parser.getint("search_intelligence", "depth") == 17
    assert parser.get("search_intelligence", "device") == "desktop"
    assert parser.getboolean("search_intelligence", "competitive") is False

    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)
    assert restored.search_queries == state.search_queries
    assert restored.search_depth == 17
    assert restored.search_region == state.search_region
    assert restored.search_device == "desktop"
    assert restored.search_competitive is False


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


def test_preparation_surface_is_result_oriented_and_returns_home(monkeypatch) -> None:
    console = ModuleType("test_console_ui_refactor_preparation")
    console.render_header = lambda state: None
    console._execution_readiness = lambda state: (True, "configuração válida")
    state = SearchConsoleState(target="https://example.com/")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "V")

    output = StringIO()
    with redirect_stdout(output):
        assert ui._preparation_menu(console, state, lambda current: "") == "V"
    rendered = output.getvalue()
    assert "PERFIL DA PRÓXIMA AUDITORIA" in rendered
    assert "ANÁLISES / RESULTADOS" in rendered
    assert "Domínio e descoberta" in rendered
    assert "Search Intelligence" in rendered
    assert "RESULTADOS SISTÊMICOS" in rendered
    assert "Mobile=INCLUÍDO" in rendered
    assert ui._get_meta(state, "preparation_active", False) is False


def test_top_level_information_architecture_routes_to_existing_actions(monkeypatch) -> None:
    import rasai.console_navigation as navigation

    console = ModuleType("test_console_ui_refactor_top")
    console.render_header = lambda state: None
    console._menu = lambda state: builtins.input("Escolha: ").strip().upper()
    navigation.install(console)
    ui._install_top_level_menu(console)
    state = SimpleNamespace(project="Projeto", target="https://example.com/", audit_id="", audits_root="audits", error="")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "4")

    output = StringIO()
    with redirect_stdout(output):
        assert console._menu(state) == "E"
    rendered = output.getvalue()
    assert "4. Inteligência Artificial" in rendered
    assert "5. Integrações e serviços" in rendered
    assert "6. Todas as configurações" in rendered
    assert ui._config_view(state) == "ai"


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

from __future__ import annotations

from rasai import console_provider_environment as facade
from rasai import console_settings
from rasai.configuration_registry import build_configuration_registry
from rasai.synthetic_profile_console_runtime import install as install_synthetic_profile_console_runtime
from rasai.synthetic_runtime_profiles import PROFILE_ENV_NAMES
from rasai.system_defaults import _patch_environment_catalog, load_system_defaults


def _install_configuration_surface() -> None:
    install_synthetic_profile_console_runtime()
    _patch_environment_catalog()
    facade.refresh_specs()


def test_registry_covers_the_installed_console_surface_and_profile_defaults() -> None:
    _install_configuration_surface()
    registry = {item.name: item for item in build_configuration_registry()}
    specs = {spec.name: spec for spec in facade.refresh_specs()}
    assert set(registry) == set(specs)

    parser = load_system_defaults()
    for name in PROFILE_ENV_NAMES:
        assert parser.has_option("environment", name)
        assert registry[name].persist_session is True
        assert registry[name].persist_ini is True
        assert registry[name].sensitive is False
        assert set(registry[name].catalog_ids) == {"CAT-06", "CAT-07"}
        assert registry[name].default == parser.get("environment", name)


def test_runtime_enriched_nonsecret_specs_are_in_the_ini_allowlist() -> None:
    _install_configuration_surface()
    allowed = set(console_settings._known_nonsecret_environment_names())
    assert set(PROFILE_ENV_NAMES) <= allowed


from rasai import console_catalog_plan as catalog_plan
from rasai.audit_catalog import CATALOGS
from rasai.console_search_intelligence import SearchConsoleState


def test_bulk_selection_marks_every_catalog_without_reselecting_existing_items() -> None:
    state = SearchConsoleState()
    catalog_plan._PLANS.clear()
    catalog_plan.set_selected_catalog_ids(state, ["CAT-01"])

    added = catalog_plan.select_all_unselected_catalogs(state)

    assert catalog_plan.selected_catalog_ids(state) == tuple(item.id for item in CATALOGS)
    assert "CAT-01" not in added
    assert set(added) == {item.id for item in CATALOGS if item.id != "CAT-01"}


def test_bulk_selection_can_exclude_immutable_catalogs_for_audit_extension() -> None:
    state = SearchConsoleState()
    catalog_plan._PLANS.clear()
    catalog_plan.set_selected_catalog_ids(state, ["CAT-06"])

    added = catalog_plan.select_all_unselected_catalogs(
        state,
        excluded_catalog_ids={"CAT-06"},
    )

    assert "CAT-06" not in added
    assert "CAT-07" in added
    assert "CAT-06" in catalog_plan.selected_catalog_ids(state)


from configparser import ConfigParser

from rasai.configuration_registry import catalog_configuration_partition
from rasai.m25_cli import UX_SAMPLES_ENV
from rasai.synthetic_runtime_profiles import PROFILE_ENV
from rasai.system_defaults import restore_catalog_defaults


def test_cat07_registry_separates_exclusive_and_shared_configuration() -> None:
    _install_configuration_surface()
    exclusive, shared = catalog_configuration_partition("CAT-07")
    exclusive_names = {item.name for item in exclusive}
    shared_names = {item.name for item in shared}

    assert UX_SAMPLES_ENV in exclusive_names
    assert set(PROFILE_ENV_NAMES) <= shared_names
    assert set(PROFILE_ENV_NAMES).isdisjoint(exclusive_names)


def test_restore_cat07_preserves_shared_profiles_and_other_catalogs(monkeypatch, tmp_path) -> None:
    _install_configuration_surface()
    state = SearchConsoleState()

    shared_profile = PROFILE_ENV[("MOBILE", "client")]
    monkeypatch.setenv("RASAI_SYNTHETIC_APDEX", "true")
    monkeypatch.setenv("RASAI_APDEX_THRESHOLD_SECONDS", "3")
    monkeypatch.setenv("RASAI_APDEX_EXPERIENCE", "true")
    monkeypatch.setenv(UX_SAMPLES_ENV, "77")
    monkeypatch.setenv("RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS", "100")
    monkeypatch.setenv(shared_profile, "mobile-compact-chromium")
    monkeypatch.setenv("RASAI_WEB_PERFORMANCE_MAX_PAGES", "99")

    apdex_issues = facade.base_environment.apply_m23_environment_defaults(state)
    web_issues = facade.base_environment.apply_environment_defaults(
        state,
        names={"RASAI_WEB_PERFORMANCE_MAX_PAGES"},
    )
    assert not apdex_issues, apdex_issues
    assert not web_issues, web_issues
    assert state.apdex_experience_samples == 77
    assert state.web_max_pages == 99

    destination = tmp_path / "rasai-console.ini"
    result = restore_catalog_defaults(state, "CAT-07", path=destination)

    assert not result.warnings, result.warnings
    assert UX_SAMPLES_ENV in result.restored_names
    assert shared_profile in result.shared_preserved
    assert state.apdex_experience_samples == 20
    assert state.web_max_pages == 99
    assert facade.base_environment.os.environ[shared_profile] == "mobile-compact-chromium"

    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(destination, encoding="utf-8")
    assert parser.get("environment", UX_SAMPLES_ENV) == "20"
    assert parser.get("environment", shared_profile) == "mobile-compact-chromium"
    assert parser.get("environment", "RASAI_WEB_PERFORMANCE_MAX_PAGES") == "99"


def test_all_settings_routes_structural_audits_root_to_canonical_editor(monkeypatch) -> None:
    import builtins
    from contextlib import redirect_stdout
    from io import StringIO
    from types import ModuleType, SimpleNamespace

    from rasai import console_ui_catalog as ui_catalog

    console = ModuleType("test_issue_160_structural_audits_root")
    calls: list[tuple[str, str]] = []
    console._configure = lambda current_state, choice: calls.append((current_state.audits_root, choice))
    state = SimpleNamespace(audits_root="audits", error="")

    monkeypatch.setattr(facade, "refresh_specs", lambda: ())
    monkeypatch.setattr(facade.base_environment, "render_header", lambda current: None)
    answers = iter([ui_catalog.CORE_IDS["audits_root"], "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    output = StringIO()
    with redirect_stdout(output):
        ui_catalog.catalog_menu(console, state, view="all", title="TODAS AS CONFIGURAÇÕES")

    rendered = output.getvalue()
    assert "CONFIGURAÇÕES ESTRUTURAIS DO CONSOLE" in rendered
    assert f"{ui_catalog.CORE_IDS['audits_root']}  Raiz das auditorias" in rendered
    assert "audits" in rendered
    assert calls == [("audits", "10")]


def test_audits_root_round_trips_through_existing_console_persistence(tmp_path) -> None:
    state = SearchConsoleState()
    state.audits_root = str(tmp_path / "custom-audits")
    destination = tmp_path / "rasai-console.ini"

    console_settings.save_console_config(state, destination)

    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)

    assert restored.audits_root == state.audits_root

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
    monkeypatch.setenv(UX_SAMPLES_ENV, "77")
    monkeypatch.setenv(shared_profile, "mobile-compact-chromium")
    monkeypatch.setenv("RASAI_WEB_PERFORMANCE_MAX_PAGES", "99")

    facade.base_environment._apply_change(state, UX_SAMPLES_ENV)
    facade.base_environment._apply_change(state, "RASAI_WEB_PERFORMANCE_MAX_PAGES")
    assert state.apdex_experience_samples == 77
    assert state.web_max_pages == 99

    destination = tmp_path / "rasai-console.ini"
    result = restore_catalog_defaults(state, "CAT-07", path=destination)

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

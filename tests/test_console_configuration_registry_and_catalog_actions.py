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

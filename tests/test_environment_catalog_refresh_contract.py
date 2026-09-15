from __future__ import annotations

from rasai import console_provider_environment as environment
from rasai.console_ui_catalog import capability_specs, catalog_specs
from rasai.system_defaults import _patch_environment_catalog


def test_system_defaults_preserves_refresh_specs_return_contract() -> None:
    _patch_environment_catalog()

    specs = environment.refresh_specs()

    assert isinstance(specs, tuple)
    assert specs is environment.SPECS
    assert specs


def test_refactored_console_catalog_remains_iterable_after_system_defaults_patch() -> None:
    _patch_environment_catalog()

    all_specs = catalog_specs("all")
    web_performance_specs = capability_specs("web-performance")

    assert isinstance(all_specs, tuple)
    assert all_specs
    assert isinstance(web_performance_specs, tuple)
    assert web_performance_specs

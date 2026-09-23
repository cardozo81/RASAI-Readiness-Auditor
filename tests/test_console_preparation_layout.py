from types import ModuleType
import inspect

from rasai import console_preparation_layout as layout


def test_preparation_layout_is_only_a_composition_marker() -> None:
    console = ModuleType("test_console_preparation_layout")
    assert not getattr(console, "_rasai_canonical_preparation_layout", False)
    layout.install(console)
    assert console._rasai_canonical_preparation_layout is True


def test_legacy_numbered_profile_dashboard_is_not_kept_in_layout_module() -> None:
    source = inspect.getsource(layout)
    assert "PERFIL DA PRÓXIMA EXECUÇÃO" not in source
    assert "_VISIBLE_TO_INTERNAL" not in source
    assert "_standardize_output" not in source

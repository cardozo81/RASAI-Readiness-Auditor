from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rasai import console_catalog_ui
from rasai import console_configuration_presentation as presentation
from rasai import console_ui_catalog
from rasai.audit_catalog import CATALOGS
from rasai.console_search_intelligence import SearchConsoleState


def test_catalog_submenu_uses_human_label_and_secondary_technical_name(monkeypatch) -> None:
    state = SearchConsoleState()
    catalog = next(item for item in CATALOGS if item.id == "CAT-06")
    specs = tuple(console_catalog_ui._related_specs(catalog))
    assert specs

    console = SimpleNamespace(
        render_header=lambda current: None,
        _configure=lambda current, choice: None,
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    output = StringIO()
    with redirect_stdout(output):
        console_catalog_ui.catalog_menu(console, state, catalog)

    rendered = output.getvalue()
    sample = specs[0]
    assert presentation.friendly_label(sample) in rendered
    assert f"Variável técnica: {sample.name}" in rendered


def test_capability_submenu_uses_human_label_and_secondary_technical_name(monkeypatch) -> None:
    state = SearchConsoleState()
    capability = next(
        item for item in console_ui_catalog.CAPABILITIES
        if item.key == "web-performance"
    )
    specs = tuple(console_ui_catalog.capability_specs(capability.key))
    assert specs

    from rasai import console_provider_environment as environment

    monkeypatch.setattr(environment.base_environment, "render_header", lambda current: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")

    output = StringIO()
    with redirect_stdout(output):
        console_ui_catalog.capability_menu(SimpleNamespace(), state, capability)

    rendered = output.getvalue()
    sample = sorted(
        specs,
        key=lambda item: (
            console_ui_catalog.owner_for(item).casefold(),
            item.name.casefold(),
        ),
    )[0]
    assert presentation.friendly_label(sample) in rendered
    assert f"Variável técnica: {sample.name}" in rendered


def test_root_cmd_shortcut_starts_interactive_console_without_iniciar_cmd() -> None:
    shortcut = Path(__file__).resolve().parents[1] / "abrir-rasai-console.cmd"
    assert shortcut.is_file()

    content = shortcut.read_text(encoding="utf-8").casefold()
    assert 'cd /d "%~dp0"' in content
    assert "rasai-console.exe" in content
    assert '"%console_exe%"' in content
    assert "iniciar.cmd" not in content

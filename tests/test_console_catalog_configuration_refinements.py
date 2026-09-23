from __future__ import annotations

from configparser import ConfigParser
import os
from types import SimpleNamespace

import pytest

from rasai import audit_catalog
from rasai import console_catalog_configuration_refinements as refinements
from rasai import console_catalog_ui
from rasai import console_catalog_plan as plan
from rasai import console_catalog_workflow as workflow
from rasai import console_configuration_context_presentation as context
from rasai import console_configuration_presentation as presentation
from rasai import console_provider_environment as environment
from rasai import console_settings
from rasai.console_search_intelligence import SearchConsoleState


@pytest.fixture(autouse=True)
def _isolate_environment_and_plan():
    before = dict(os.environ)
    plan._PLANS.clear()
    try:
        yield
    finally:
        plan._PLANS.clear()
        os.environ.clear()
        os.environ.update(before)


def _spec(name: str):
    return next(spec for spec in environment.refresh_specs() if spec.name == name)


def test_catalog_selection_round_trips_through_console_ini(tmp_path) -> None:
    original_values = console_settings._state_values
    original_assign = console_settings._assign
    had_flag = hasattr(console_settings, "_rasai_catalog_plan_persistence")
    original_flag = getattr(console_settings, "_rasai_catalog_plan_persistence", None)
    if had_flag:
        delattr(console_settings, "_rasai_catalog_plan_persistence")

    try:
        refinements._install_catalog_ini_persistence()
        state = SearchConsoleState()
        plan.set_selected_catalog_ids(state, ["CAT-01", "CAT-05", "CAT-07"])
        plan.set_ai_execution_enabled(state, False)

        destination = tmp_path / "rasai-console.ini"
        console_settings.save_console_config(state, destination)

        parser = ConfigParser(interpolation=None)
        parser.read(destination, encoding="utf-8")
        assert parser.get("audit_catalog", "selected") == "CAT-01, CAT-05, CAT-06, CAT-07"
        assert parser.getboolean("audit_catalog", "ai_enabled") is False

        plan._PLANS.clear()
        restored = SearchConsoleState()
        console_settings.load_console_config(restored, destination)
        assert plan.selected_catalog_ids(restored) == (
            "CAT-01",
            "CAT-05",
            "CAT-06",
            "CAT-07",
        )
        assert plan.ai_execution_enabled(restored) is False
    finally:
        console_settings._state_values = original_values
        console_settings._assign = original_assign
        if had_flag:
            console_settings._rasai_catalog_plan_persistence = original_flag
        elif hasattr(console_settings, "_rasai_catalog_plan_persistence"):
            delattr(console_settings, "_rasai_catalog_plan_persistence")




def test_catalog_ini_restores_no_ai_choice_with_cat08_selected(tmp_path) -> None:
    original_values = console_settings._state_values
    original_assign = console_settings._assign
    had_flag = hasattr(console_settings, "_rasai_catalog_plan_persistence")
    original_flag = getattr(console_settings, "_rasai_catalog_plan_persistence", None)
    if had_flag:
        delattr(console_settings, "_rasai_catalog_plan_persistence")

    try:
        refinements._install_catalog_ini_persistence()
        state = SearchConsoleState()
        plan.set_selected_catalog_ids(state, ["CAT-01", "CAT-08"])
        plan.set_ai_execution_enabled(state, False)

        destination = tmp_path / "rasai-console.ini"
        console_settings.save_console_config(state, destination)

        plan._PLANS.clear()
        restored = SearchConsoleState()
        console_settings.load_console_config(restored, destination)

        assert "CAT-08" in plan.selected_catalog_ids(restored)
        assert plan.ai_execution_enabled(restored) is False
    finally:
        console_settings._state_values = original_values
        console_settings._assign = original_assign
        if had_flag:
            console_settings._rasai_catalog_plan_persistence = original_flag
        elif hasattr(console_settings, "_rasai_catalog_plan_persistence"):
            delattr(console_settings, "_rasai_catalog_plan_persistence")


def test_long_configuration_label_does_not_shift_value_or_origin(monkeypatch) -> None:
    original = presentation.format_configuration_row
    try:
        refinements._install_aligned_rows()
        spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
        state = SearchConsoleState()
        monkeypatch.setenv(spec.name, "3")

        monkeypatch.setattr(presentation, "friendly_label", lambda current: "Curto")
        short = refinements._plain(presentation.format_configuration_row(state, spec))
        monkeypatch.setattr(
            presentation,
            "friendly_label",
            lambda current: "Descrição extremamente longa que antes deslocava todas as colunas seguintes",
        )
        long = refinements._plain(presentation.format_configuration_row(state, spec))

        assert "…" in long
        assert short.index("3 s") == long.index("3 s")
        assert short.rindex("[") == long.rindex("[")
        assert "Variável técnica: RASAI_APDEX_THRESHOLD_SECONDS" in short
        assert "Variável técnica: RASAI_APDEX_THRESHOLD_SECONDS" in long
    finally:
        presentation.format_configuration_row = original


def test_source_specific_groups_are_explicit() -> None:
    original = context._functional_group
    try:
        refinements._install_functional_groups()
        cases = {
            "RASAI_CRUX_HISTORY_ENABLED": "CrUX History — experiência real histórica",
            "RASAI_CLARITY_DAYS": "Microsoft Clarity — comportamento real",
            "RASAI_COMMON_CRAWL_MAX_URLS": "Common Crawl — histórico público",
            "RASAI_DYNATRACE_BASE_URL": "Dynatrace — calibração/importação opcional",
        }
        for name, expected in cases.items():
            major, subgroup = context._functional_group(SimpleNamespace(name=name))
            assert major == expected
            assert subgroup is None
    finally:
        context._functional_group = original


def test_cat05_shared_crux_key_stays_inside_crux_history_group() -> None:
    major, subgroup = refinements._functional_group_for_catalog(
        "CAT-05", SimpleNamespace(name="RASAI_CRUX_API_KEY")
    )
    assert major == "CrUX History — experiência real histórica"
    assert subgroup == "Credencial"


def test_related_row_parser_accepts_canonical_configuration_ids() -> None:
    current = refinements._ROW_RE.match("12345678  Modo de coleta SERP")
    assert current is not None and current.group(1) == "12345678"
    assert refinements._ROW_RE.match("598690  Modo de coleta SERP") is None


def test_cat05_sources_are_ordered_and_cat07_dynatrace_is_last(monkeypatch) -> None:
    groups = {
        "serp": "SERP — resultados públicos por termo",
        "gsc": "Google Search Console — dados da property autenticada",
        "crux": "CrUX History — experiência real histórica",
        "clarity": "Microsoft Clarity — comportamento real",
        "crawl": "Common Crawl — histórico público",
        "apdex": "Apdex de experiência",
        "dynatrace": "Dynatrace — calibração/importação opcional",
    }
    monkeypatch.setattr(
        context,
        "_functional_group",
        lambda spec: (groups[spec.name], None),
    )
    monkeypatch.setattr(presentation, "friendly_label", lambda spec: spec.name)

    cat05 = tuple(SimpleNamespace(name=name) for name in ("crawl", "clarity", "gsc", "serp", "crux"))
    ordered = refinements.sort_related_specs("CAT-05", cat05)
    assert [item.name for item in ordered] == ["serp", "gsc", "crux", "clarity", "crawl"]

    cat07 = tuple(SimpleNamespace(name=name) for name in ("dynatrace", "apdex"))
    ordered = refinements.sort_related_specs("CAT-07", cat07)
    assert [item.name for item in ordered] == ["apdex", "dynatrace"]


def test_remove_action_returns_to_origin_and_unselects_every_catalog(monkeypatch) -> None:
    original_menu = console_catalog_ui.catalog_menu
    original_related = console_catalog_ui._related_specs
    original_workflow_menu = workflow.catalog_menu
    original_workflow_alias = workflow._catalog_menu
    try:
        console_catalog_ui._related_specs = lambda catalog: ()

        observed: list[tuple[str, str]] = []

        def inner(console, state, catalog):
            observed.append((catalog.id, input("Número/ID ou ação: ").strip().upper()))

        console_catalog_ui.catalog_menu = inner
        monkeypatch.setattr("builtins.input", lambda prompt="": "D")
        refinements._install_catalog_copy()

        console = SimpleNamespace()
        for catalog in audit_catalog.CATALOGS:
            state = SearchConsoleState()
            plan.set_selected_catalog_ids(state, [catalog.id])
            console_catalog_ui.catalog_menu(console, state, catalog)
            assert catalog.id not in plan.selected_catalog_ids(state)
            assert observed[-1] == (catalog.id, "V")
    finally:
        console_catalog_ui.catalog_menu = original_menu
        console_catalog_ui._related_specs = original_related
        workflow.catalog_menu = original_workflow_menu
        workflow._catalog_menu = original_workflow_alias


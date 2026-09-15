from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
import os
from types import ModuleType, SimpleNamespace

import pytest

from rasai import audit_catalog
from rasai import console_catalog_workflow as workflow
from rasai import console_catalog_plan as plan_module
from rasai import console_catalog_ui as catalog_ui


def _state(**overrides):
    values = {
        "target": "https://example.com/",
        "project": "",
        "device": "mobile",
        "language": "pt-BR",
        "market": "BR",
        "audits_root": "audits",
        "web_performance": False,
        "field_source": "auto",
        "lighthouse_categories": "performance",
        "search_queries": (),
        "search_depth": 20,
        "search_region": "",
        "search_device": "mobile",
        "search_competitive": True,
        "synthetic_apdex": False,
        "apdex_experience": False,
        "improvement_enabled": False,
        "content_remediation": False,
        "technical_remediation": False,
        "ai_provider": "none",
        "ai_model": None,
        "ai_reasoning": None,
        "runtime_blocks": {},
        "error": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _isolate_plan_and_environment():
    environment = dict(os.environ)
    workflow._PLANS.clear()
    try:
        yield
    finally:
        workflow._PLANS.clear()
        os.environ.clear()
        os.environ.update(environment)


def test_catalog_has_stable_unique_report_ready_ids() -> None:
    assert audit_catalog.CATALOG_VERSION == "1"
    assert [item.id for item in audit_catalog.CATALOGS] == [f"CAT-{index:02d}" for index in range(1, 10)]
    assert len(audit_catalog.CATALOG_BY_ID) == 9
    assert "quality" in audit_catalog.SYSTEM_DERIVED_CAPABILITY_IDS
    assert audit_catalog.CATALOG_BY_ID["CAT-05"].capability_ids == (
        "search-intelligence",
        "google-search-console",
        "ai-visibility",
        "observability",
    )




def test_ai_usage_is_limited_to_actual_ai_consumers() -> None:
    modes = {item.id: item.ai_mode for item in audit_catalog.CATALOGS}
    assert modes["CAT-03"] == audit_catalog.AI_OPTIONAL
    assert modes["CAT-08"] == audit_catalog.AI_REQUIRED
    assert modes["CAT-09"] == audit_catalog.AI_OPTIONAL
    for catalog_id in ("CAT-01", "CAT-02", "CAT-04", "CAT-05", "CAT-06", "CAT-07"):
        assert modes[catalog_id] == audit_catalog.AI_NONE


def test_optional_ai_defaults_to_off_even_when_provider_is_configured() -> None:
    state = _state(ai_provider="auto")
    workflow.set_selected_catalog_ids(state, ["CAT-03"])
    assert workflow.ai_execution_enabled(state) is False
    assert workflow.plan_status(state)[0] == "APTO"


def test_optional_ai_can_be_explicitly_enabled_and_is_then_projected() -> None:
    state = _state(ai_provider="auto")
    workflow.set_selected_catalog_ids(state, ["CAT-03"])
    workflow.set_ai_execution_enabled(state, True)
    assert workflow.ai_execution_enabled(state) is True
    with workflow._project_execution_plan(state):
        assert state.ai_provider == "auto"


def test_optional_ai_choice_requires_an_eligible_primary_provider() -> None:
    state = _state(ai_provider="none")
    workflow.set_selected_catalog_ids(state, ["CAT-03"])
    workflow.set_ai_execution_enabled(state, True)
    status, detail = workflow.plan_status(state)
    assert status == "BLOQUEADO"
    assert "IA principal" in detail


def test_optional_ai_enabled_requires_registry_readiness(monkeypatch) -> None:
    state = _state(ai_provider="auto")
    workflow.set_selected_catalog_ids(state, ["CAT-03"])
    workflow.set_ai_execution_enabled(state, True)
    monkeypatch.setattr(plan_module, "ai_provider_readiness", lambda current: (False, "sem credencial"))
    status, detail = workflow.plan_status(state)
    assert status == "BLOQUEADO"
    assert "sem credencial" in detail

def test_selecting_experience_apdex_adds_navigation_dependency() -> None:
    state = _state()
    workflow._select(state, audit_catalog.CATALOG_BY_ID["CAT-07"])
    assert workflow.selected_catalog_ids(state) == ("CAT-06", "CAT-07")


def test_plan_requires_at_least_one_catalog() -> None:
    state = _state()
    assert workflow.plan_status(state)[0] == "BLOQUEADO"


def test_web_performance_readiness_tracks_its_effective_configuration(monkeypatch) -> None:
    state = _state()
    workflow._select(state, audit_catalog.CATALOG_BY_ID["CAT-04"])
    status, detail = workflow.catalog_status(state, audit_catalog.CATALOG_BY_ID["CAT-04"])
    assert status == "BLOQUEADO"
    assert "desabilitado" in detail.casefold()

    state.web_performance = True
    monkeypatch.setattr(plan_module, "_single_status", lambda current, key: ("APTO", "ok"))
    assert workflow.catalog_status(state, audit_catalog.CATALOG_BY_ID["CAT-04"]) == ("APTO", "ok")


def test_deep_analysis_requires_producer_and_ai(monkeypatch) -> None:
    state = _state(improvement_enabled=True)
    workflow.set_selected_catalog_ids(state, ["CAT-01", "CAT-08"])
    assert workflow.ai_execution_enabled(state) is True
    monkeypatch.setattr(plan_module, "_single_status", lambda current, key: ("APTO", "ok"))
    assert workflow.plan_status(state)[0] == "BLOQUEADO"
    state.ai_provider = "auto"
    monkeypatch.setattr(plan_module, "ai_provider_readiness", lambda current: (True, "ok"))
    assert workflow.plan_status(state)[0] == "APTO"


def test_execution_projection_masks_unselected_optional_state_and_restores_it() -> None:
    state = _state(
        web_performance=True,
        search_queries=("seguro",),
        synthetic_apdex=True,
        apdex_experience=True,
        improvement_enabled=True,
        content_remediation=True,
        technical_remediation=True,
        ai_provider="auto",
    )
    workflow.set_selected_catalog_ids(state, ["CAT-01"])
    os.environ["RASAI_GSC_ENABLED"] = "true"
    os.environ["RASAI_COMMON_CRAWL_ENABLED"] = "true"
    os.environ["RASAI_CLARITY_ENABLED"] = "true"

    with workflow._project_execution_plan(state):
        assert state.web_performance is False
        assert state.search_queries == ()
        assert state.synthetic_apdex is False
        assert state.apdex_experience is False
        assert state.improvement_enabled is False
        assert state.content_remediation is False
        assert state.technical_remediation is False
        assert state.ai_provider == "none"
        assert os.environ["RASAI_GSC_ENABLED"] == "false"
        assert os.environ["RASAI_COMMON_CRAWL_ENABLED"] == "false"
        assert os.environ["RASAI_CLARITY_ENABLED"] == "false"

    assert state.web_performance is True
    assert state.search_queries == ("seguro",)
    assert state.synthetic_apdex is True
    assert state.apdex_experience is True
    assert state.improvement_enabled is True
    assert state.content_remediation is True
    assert state.technical_remediation is True
    assert state.ai_provider == "auto"
    assert os.environ["RASAI_GSC_ENABLED"] == "true"
    assert os.environ["RASAI_COMMON_CRAWL_ENABLED"] == "true"
    assert os.environ["RASAI_CLARITY_ENABLED"] == "true"


def test_optional_ai_off_masks_provider_and_ai_remediation_without_changing_session() -> None:
    state = _state(
        content_remediation=True,
        technical_remediation=True,
        ai_provider="auto",
        ai_model="model-x",
        ai_reasoning="low",
    )
    workflow.set_selected_catalog_ids(state, ["CAT-01", "CAT-09"])
    workflow.set_ai_execution_enabled(state, False)

    with workflow._project_execution_plan(state):
        assert state.ai_provider == "none"
        assert state.ai_model is None
        assert state.ai_reasoning is None
        assert state.content_remediation is False
        assert state.technical_remediation is False

    assert state.ai_provider == "auto"
    assert state.ai_model == "model-x"
    assert state.ai_reasoning == "low"
    assert state.content_remediation is True
    assert state.technical_remediation is True


def test_selecting_catalog_opens_its_configuration_immediately(monkeypatch) -> None:
    console = ModuleType("test_catalog_preparation")
    console.render_header = lambda state: None
    console._execution_readiness = lambda state: (True, "configuração válida")
    console._configure = lambda state, choice: None
    state = _state()
    opened: list[str] = []

    def catalog_menu(current_console, current_state, catalog):
        opened.append(catalog.id)

    monkeypatch.setattr(catalog_ui, "catalog_menu", catalog_menu)
    answers = iter(["6", "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    output = StringIO()
    with redirect_stdout(output):
        assert workflow.preparation_menu(console, state) == "V"

    rendered = output.getvalue()
    assert opened == ["CAT-01"]
    assert workflow.selected_catalog_ids(state) == ("CAT-01",)
    assert "CATÁLOGO DA AUDITORIA" in rendered
    assert "PERFIL DA PRÓXIMA AUDITORIA" not in rendered
    assert "ANÁLISES / RESULTADOS" not in rendered


def test_catalog_snapshot_is_stable_for_future_report_projection() -> None:
    state = _state()
    workflow.set_selected_catalog_ids(state, ["CAT-01", "CAT-03"])
    rows = workflow.catalog_snapshot(state)
    selected = [row for row in rows if row["selected"]]
    assert [row["catalog_id"] for row in selected] == ["CAT-01", "CAT-03"]
    assert all(row["catalog_version"] == "1" for row in rows)
    assert selected[1]["ai_mode"] == "OPTIONAL"
    assert selected[1]["ai_execution_enabled"] is False
    assert "capability_ids" in selected[0]
    workflow.set_ai_execution_enabled(state, True)
    selected = [row for row in workflow.catalog_snapshot(state) if row["selected"]]
    assert selected[1]["ai_execution_enabled"] is True


def test_install_wraps_execution_with_selected_plan(monkeypatch) -> None:
    console = ModuleType("test_catalog_install")
    observed: list[tuple[bool, tuple[str, ...]]] = []

    def run(state):
        observed.append((state.web_performance, tuple(state.search_queries)))
        return 0

    console.run_audit_from_console = run
    state = _state(web_performance=True, search_queries=("seguro",))
    workflow.set_selected_catalog_ids(state, ["CAT-01"])
    monkeypatch.setattr(workflow, "_install_configuration_reuse_contract", lambda: None)

    workflow._install_execution_projection(console)
    assert console.run_audit_from_console(state) == 0
    assert observed == [(False, ())]
    assert state.web_performance is True
    assert state.search_queries == ("seguro",)

def test_catalog_guidance_removes_superseded_item_references() -> None:
    assert workflow._rewrite_catalog_guidance("configure IA no item 4") == (
        "configure IA no I. Inteligência Artificial"
    )
    assert workflow._rewrite_catalog_guidance("retorne ao item 13") == "retorne ao CAT-08"
    assert workflow._rewrite_catalog_guidance("configure termos no item T") == (
        "configure termos no CAT-05"
    )


def test_catalog_guidance_wraps_console_configure_without_changing_handler(monkeypatch) -> None:
    console = ModuleType("test_catalog_guidance")
    calls: list[str] = []

    def configure(state, choice):
        calls.append(choice)
        print("IA ativa no item 4")
        state.error = "configure IA no item 4"

    console._configure = configure
    state = _state()
    monkeypatch.setattr(workflow, "_install_configuration_reuse_contract", lambda: None)
    monkeypatch.setattr(workflow, "_install_execution_projection", lambda module: None)

    workflow._install_catalog_guidance(console)
    with redirect_stdout(StringIO()) as output:
        console._configure(state, "5")

    assert calls == ["5"]
    assert "I. Inteligência Artificial" in output.getvalue()
    assert "item 4" not in output.getvalue()
    assert "I. Inteligência Artificial" in state.error

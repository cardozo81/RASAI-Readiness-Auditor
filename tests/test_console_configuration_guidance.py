from __future__ import annotations

from dataclasses import replace
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from rasai.console_config import State
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_runtime import install_pre_context


def _installed_facade():
    install_pre_context()
    install_standards_console_runtime()
    from rasai import console_provider_environment as facade

    facade.refresh_specs()
    return facade


def test_environment_menu_explains_flow_defaults_and_secret_boundaries() -> None:
    facade = _installed_facade()
    state = State()
    output = io.StringIO()

    with patch.object(facade.base_environment, "render_header"), patch("builtins.input", return_value="V"), redirect_stdout(output):
        facade.environment_menu(state)

    rendered = output.getvalue()
    assert "FLUXO RECOMENDADO" in rendered
    assert "AUTO/Padrão" in rendered
    assert "Secrets nunca entram no INI" in rendered
    assert "Métricas e padrões" in rendered
    assert "definidos" in rendered


def test_metrics_category_guidance_connects_gsc_pagespeed_and_crux_contexts() -> None:
    facade = _installed_facade()
    metrics = tuple(spec for spec in facade.SPECS if spec.category == "Métricas e padrões")
    assert metrics

    output = io.StringIO()
    with patch.object(facade.base_environment, "render_header"), patch("builtins.input", return_value="V"), redirect_stdout(output):
        facade._category_menu(State(), "Métricas e padrões", metrics)

    rendered = output.getvalue()
    assert "Google Search Console" in rendered or "GSC" in rendered
    assert "Search Intelligence / Observability" in rendered
    assert "PageSpeed/CrUX" in rendered
    assert "Mostrar somente definidas" in rendered


def test_nonsecret_variable_screen_distinguishes_default_from_override() -> None:
    facade = _installed_facade()
    spec = next(item for item in facade.SPECS if item.name == "RASAI_STANDARDS_MAX_URLS")
    output = io.StringIO()

    with patch.dict("os.environ", {}, clear=False), patch.object(facade.base_environment, "render_header"), patch("builtins.input", return_value="V"), redirect_stdout(output):
        facade._variable_menu(State(), spec)

    rendered = output.getvalue()
    assert "Estado de decisão" in rendered
    assert "usando default do runtime" in rendered
    assert "Nenhuma ação é necessária" in rendered
    assert "Remover override e voltar ao default" in rendered


def test_standards_console_install_repairs_catalog_drift_after_prior_install() -> None:
    facade = _installed_facade()
    base = facade.base_environment

    drifted = tuple(
        replace(spec, category="Aplicação e execução", default=None)
        if spec.name == "RASAI_STANDARDS_MAX_URLS"
        else spec
        for spec in base.SPECS
    )
    base.SPECS = drifted
    base.SPEC_BY_NAME = {spec.name: spec for spec in drifted}
    base._rasai_standards_service_catalog = True

    install_standards_console_runtime()
    facade.refresh_specs()

    healed = next(item for item in facade.SPECS if item.name == "RASAI_STANDARDS_MAX_URLS")
    assert healed.category == "Métricas e padrões"
    assert healed.default == "10"

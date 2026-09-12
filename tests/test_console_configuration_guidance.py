from __future__ import annotations

from dataclasses import replace
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from rasai.console_config import State
from rasai.console_configuration_guidance import (
    context_for,
    grouped_by_context,
    normalize_spec,
    prompt_guided_value,
    reference_lines,
)
from rasai.console_environment import EnvironmentSpec
from rasai.provider_registry import get_provider_registration
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_runtime import install_pre_context
from rasai.synthetic_profile_console_runtime import install as install_synthetic_profile_console_runtime


def _installed_facade():
    # Compose only configuration-related installers. Calling the broad context-scope
    # installer here would also mutate report presentation and make this test module
    # order-dependent with unrelated report tests.
    install_pre_context()
    install_standards_console_runtime()
    install_synthetic_profile_console_runtime()
    install_runtime_completion_extensions()
    install_standards_console_runtime()
    install_synthetic_profile_console_runtime()
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
    assert "valores fechados" in rendered.casefold()
    assert "definidos" in rendered


def test_metrics_category_groups_related_external_services_by_context() -> None:
    facade = _installed_facade()
    metrics = tuple(spec for spec in facade.SPECS if spec.category == "Métricas e padrões")
    assert metrics

    output = io.StringIO()
    with patch.object(facade.base_environment, "render_header"), patch("builtins.input", return_value="V"), redirect_stdout(output):
        facade._category_menu(State(), "Métricas e padrões", metrics)

    rendered = output.getvalue()
    assert "[Google Search Console]" in rendered
    assert "PageSpeed" in rendered
    assert "CrUX" in rendered
    assert "Mostrar somente definidas" in rendered


def test_nonsecret_variable_screen_distinguishes_default_from_override() -> None:
    facade = _installed_facade()
    spec = next(item for item in facade.SPECS if item.name == "RASAI_STANDARDS_MAX_URLS")
    output = io.StringIO()

    with patch.dict("os.environ", {}, clear=False), patch.object(facade.base_environment, "render_header"), patch("builtins.input", return_value="V"), redirect_stdout(output):
        facade._variable_menu(State(), spec)

    rendered = output.getvalue()
    assert "Estado de decisão" in rendered
    assert "PADRÃO" in rendered
    assert "usando default do runtime" in rendered
    assert "Nenhuma ação é necessária" in rendered
    assert "Remover override e voltar ao default/auto" in rendered
    assert "Contexto" in rendered
    assert "Como preencher" in rendered


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


def test_boolean_without_explicit_domain_is_normalized_to_canonical_choices() -> None:
    spec = EnvironmentSpec(
        "RASAI_TEST_BOOLEAN",
        "Teste",
        "Toggle de teste.",
        "booleano",
    )
    normalized = normalize_spec(spec)
    assert normalized.accepted == ("true", "false")
    assert prompt_guided_value(normalized, lambda _: "1") == "true"
    assert prompt_guided_value(normalized, lambda _: "2") == "false"


def test_known_csv_domain_uses_multi_selection_instead_of_free_text() -> None:
    spec = EnvironmentSpec(
        "RASAI_LIGHTHOUSE_CATEGORIES",
        "Web Performance / Google APIs",
        "Categorias Lighthouse.",
        "lista CSV",
        ("performance", "accessibility", "best-practices", "seo"),
        "performance,accessibility",
    )
    assert prompt_guided_value(spec, lambda _: "1,4") == "performance,seo"
    assert prompt_guided_value(spec, lambda _: "todos") == "performance,accessibility,best-practices,seo"


def test_oidc_algorithm_list_is_completed_from_known_runtime_domain() -> None:
    spec = EnvironmentSpec(
        "RASAI_OIDC_ALGORITHMS",
        "Web API / Identity",
        "Algoritmos JWT aceitos.",
        "lista CSV",
        default="RS256,ES256",
    )
    normalized = normalize_spec(spec)
    assert normalized.accepted == ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")


def test_context_grouping_keeps_related_gsc_variables_together() -> None:
    specs = (
        EnvironmentSpec("RASAI_GSC_ENABLED", "Métricas e padrões", "GSC toggle", "booleano"),
        EnvironmentSpec(
            "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
            "Métricas e padrões",
            "GSC property",
            "texto",
        ),
        EnvironmentSpec("RASAI_CRUX_ENABLED", "Métricas e padrões", "CrUX toggle", "booleano"),
    )
    assert context_for(specs[0]) == "Google Search Console"
    assert context_for(specs[1]) == "Google Search Console"
    grouped = grouped_by_context(specs)
    assert grouped[0][0] == "Google Search Console"
    assert tuple(row[1].name for row in grouped[0][1]) == (
        "RASAI_GSC_ENABLED",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
    )


def test_registry_backed_external_services_expose_official_references() -> None:
    gsc = EnvironmentSpec(
        "RASAI_GSC_ENABLED",
        "Métricas e padrões",
        "Google Search Console",
        "booleano",
    )
    gsc_refs = reference_lines(gsc)
    assert any("developers.google.com/webmaster-tools" in item for item in gsc_refs)
    assert any("console.cloud.google.com/apis/credentials" in item for item in gsc_refs)

    pagespeed = EnvironmentSpec(
        "RASAI_PAGESPEED_API_KEY",
        "Web Performance / Google APIs",
        "PageSpeed key",
        "segredo/API key",
        sensitive=True,
    )
    page_refs = reference_lines(pagespeed)
    assert any("developers.google.com/speed" in item for item in page_refs)
    assert any("console.cloud.google.com/apis/credentials" in item for item in page_refs)


def test_all_closed_domain_variables_are_guided_after_runtime_composition() -> None:
    facade = _installed_facade()
    for spec in facade.SPECS:
        normalized = normalize_spec(spec)
        if str(normalized.value_type).casefold() in {"booleano", "enum", "enum inteiro"}:
            assert normalized.accepted, normalized.name
        assert normalized.purpose != "Variável reconhecida pelo RASAi.", normalized.name
        assert normalized.purpose.strip(), normalized.name
        assert normalized.required_when.strip(), normalized.name
        assert normalized.impact.strip(), normalized.name


def test_gsc_toggle_uses_boolean_choice_and_context_metadata() -> None:
    facade = _installed_facade()
    spec = normalize_spec(facade.SPEC_BY_NAME["RASAI_GSC_ENABLED"])
    assert spec.accepted == ("true", "false")
    assert context_for(spec) == "Google Search Console"
    assert any("webmaster-tools" in item for item in reference_lines(spec))


def test_improvement_model_and_reasoning_choices_follow_selected_provider() -> None:
    facade = _installed_facade()
    registration = get_provider_registration("openai")
    assert registration is not None
    with patch.dict("os.environ", {"RASAI_IMPROVEMENT_AI_PROVIDER": "openai"}, clear=False):
        model = normalize_spec(facade.SPEC_BY_NAME["RASAI_IMPROVEMENT_AI_MODEL"])
        reasoning = normalize_spec(facade.SPEC_BY_NAME["RASAI_IMPROVEMENT_AI_REASONING"])
    assert model.value_type == "enum"
    assert model.accepted == registration.supported_models
    assert reasoning.value_type == "enum"
    assert reasoning.accepted == registration.reasoning_values


def test_advanced_ai_variables_have_specific_metadata_not_generic_fallback() -> None:
    facade = _installed_facade()
    exchange = normalize_spec(facade.SPEC_BY_NAME["RASAI_AI_EXCHANGE_LOG_MAX_BYTES"])
    exclusions = normalize_spec(facade.SPEC_BY_NAME["RASAI_AI_AUTO_EXCLUDE"])
    assert exchange.default == "524288"
    assert "request/response" in exchange.purpose
    assert exclusions.value_type == "lista CSV"
    assert exclusions.accepted
    assert "AI=auto" in exclusions.purpose

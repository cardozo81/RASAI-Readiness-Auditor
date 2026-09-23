from types import SimpleNamespace

from rasai.console_content_capability_refinements import (
    _content_component_states,
    _content_overall_status,
    _editorial_context_status,
    _property_context_status,
    _semantic_ai_status,
    _trust_context_status,
    install,
)
from rasai.property_semantic_profile import PROPERTY_SEMANTIC_PROFILE_ENV_NAMES


def _clear_context(monkeypatch) -> None:
    for name in (
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_YMYL_CATEGORY",
        "RASAI_PAGE_PURPOSE",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_CONTENT_ORIGIN",
        *PROPERTY_SEMANTIC_PROFILE_ENV_NAMES,
    ):
        monkeypatch.delenv(name, raising=False)


def test_content_capability_is_included_with_deterministic_components(monkeypatch):
    _clear_context(monkeypatch)
    state = SimpleNamespace(content_remediation=False, ai_provider="none", runtime_blocks={})

    status, detail = _content_overall_status(state)
    components = {label: component_status for label, component_status, _ in _content_component_states(state)}

    assert status == "INCLUÍDO"
    assert "propriedade=AUTOMÁTICO" in detail
    assert "editorial=AUTOMÁTICO" in detail
    assert "risco=AUTOMÁTICO" in detail
    assert components["Conteúdo / estrutura"] == "INCLUÍDO"
    assert components["JSON-LD"] == "INCLUÍDO"
    assert components["Contexto da propriedade"] == "AUTOMÁTICO"
    assert components["Contexto editorial"] == "AUTOMÁTICO"
    assert components["Risco / confiança"] == "AUTOMÁTICO"
    assert components["Coerência semântica IA"] == "NÃO SOLICITADA"
    assert "Remediação por IA" not in components


def test_explicit_property_and_editorial_context_are_personalized(monkeypatch):
    _clear_context(monkeypatch)
    monkeypatch.setenv("RASAI_PROPERTY_BUSINESS_SECTOR", "Software B2B")
    monkeypatch.setenv("RASAI_PAGE_PURPOSE", "product-service")

    property_status, property_detail = _property_context_status()
    editorial_status, editorial_detail = _editorial_context_status()

    assert property_status == "PERSONALIZADO"
    assert "business_sector" in property_detail
    assert editorial_status == "PERSONALIZADO"
    assert "page_purpose" in editorial_detail


def test_invalid_ymyl_combination_requires_configuration(monkeypatch):
    _clear_context(monkeypatch)
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "standard")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "health-safety")

    status, detail = _trust_context_status()

    assert status == "CONFIGURAR"
    assert "YMYL category" in detail
    assert "content risk profile is standard" in detail


def test_requested_semantic_ai_uses_global_readiness(monkeypatch):
    from rasai.console_catalog_plan import set_ai_execution_enabled, set_selected_catalog_ids

    _clear_context(monkeypatch)
    state = SimpleNamespace(
        ai_provider="none",
        runtime_blocks={},
        web_performance=False,
        search_queries=(),
        synthetic_apdex=False,
        apdex_experience=False,
        improvement_enabled=False,
        content_remediation=False,
        technical_remediation=False,
    )
    set_selected_catalog_ids(state, ("CAT-03",))
    set_ai_execution_enabled(state, True)

    status, detail = _semantic_ai_status(state)

    assert status == "CONFIGURAR"
    assert "IA principal" in detail


def test_content_capability_exposes_semantic_context_but_not_remediation():
    from rasai import console_ui_catalog as catalog
    from rasai.semantic_context_console import install as install_semantic_context_console

    install_semantic_context_console()
    console = SimpleNamespace()
    install(console)

    names = {item.name for item in catalog.capability_specs("content-suggestions")}

    assert "RASAI_AI_CONTENT_REMEDIATION" not in names
    assert "RASAI_AI_ANALYSIS_LANGUAGE" in names
    assert {
        "RASAI_CONTENT_ORIGIN",
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_PAGE_PURPOSE",
        "RASAI_YMYL_CATEGORY",
        *PROPERTY_SEMANTIC_PROFILE_ENV_NAMES,
    }.issubset(names)

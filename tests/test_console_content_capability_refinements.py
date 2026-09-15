from types import SimpleNamespace

from rasai.console_content_capability_refinements import (
    _content_ai_status,
    _content_component_states,
    _content_overall_status,
    _editorial_context_status,
    install,
)


def test_content_capability_is_included_with_deterministic_components(monkeypatch):
    for name in (
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_YMYL_CATEGORY",
        "RASAI_PAGE_PURPOSE",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_CONTENT_ORIGIN",
    ):
        monkeypatch.delenv(name, raising=False)

    state = SimpleNamespace(content_remediation=False, ai_provider="none", runtime_blocks={})

    status, detail = _content_overall_status(state)
    components = {label: component_status for label, component_status, _ in _content_component_states(state)}

    assert status == "INCLUÍDO"
    assert "contexto editorial=AUTOMÁTICO" in detail
    assert components["Conteúdo / estrutura"] == "INCLUÍDO"
    assert components["JSON-LD"] == "INCLUÍDO"
    assert components["Contexto editorial"] == "AUTOMÁTICO"
    assert components["Remediação por IA"] == "NÃO SOLICITADA"


def test_explicit_editorial_context_is_personalized(monkeypatch):
    monkeypatch.setenv("RASAI_PAGE_PURPOSE", "product-service")
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "auto")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "auto")
    monkeypatch.setenv("RASAI_INTENDED_AUDIENCE", "auto")
    monkeypatch.setenv("RASAI_EXPERIENCE_REQUIREMENT", "auto")
    monkeypatch.setenv("RASAI_FRESHNESS_SENSITIVITY", "auto")
    monkeypatch.setenv("RASAI_CONTENT_ORIGIN", "auto")

    status, detail = _editorial_context_status()

    assert status == "PERSONALIZADO"
    assert "page_purpose" in detail


def test_invalid_editorial_combination_requires_configuration(monkeypatch):
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "standard")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "health-safety")

    status, detail = _editorial_context_status()

    assert status == "CONFIGURAR"
    assert "invalid content analysis context" in detail


def test_requested_ai_remediation_without_apt_primary_ai_requires_configuration(monkeypatch):
    from rasai import console_execution_profiles as profiles

    monkeypatch.setattr(profiles, "_effective_ai_provider", lambda _state: "none")
    state = SimpleNamespace(content_remediation=True, ai_provider="none", runtime_blocks={})

    status, detail = _content_ai_status(state)

    assert status == "CONFIGURAR"
    assert "nenhuma IA principal" in detail


def test_content_capability_exposes_only_editorial_and_content_ai_settings():
    from rasai import console_ui_catalog as catalog

    console = SimpleNamespace()
    install(console)

    names = {item.name for item in catalog.capability_specs("content-suggestions")}

    assert names == {
        "RASAI_AI_CONTENT_REMEDIATION",
        "RASAI_AI_ANALYSIS_LANGUAGE",
        "RASAI_CONTENT_ORIGIN",
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_PAGE_PURPOSE",
        "RASAI_YMYL_CATEGORY",
    }

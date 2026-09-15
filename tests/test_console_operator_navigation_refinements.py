from types import SimpleNamespace

from rasai.console_operator_navigation_refinements import (
    _choose_audit_factory,
    _gsc_status,
    _install_search_capability_split,
    _repair_service_toggle_domains,
    _search_intelligence_status,
)


def test_manual_audit_id_accepts_v_as_clean_cancel(monkeypatch):
    from rasai import console_navigation as navigation

    monkeypatch.setattr(navigation, "_audit_directories", lambda _root: [])
    answers = iter(("I", "V", "V"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    state = SimpleNamespace(audits_root="audits", error="erro anterior")
    console = SimpleNamespace(render_header=lambda _state: None)

    assert _choose_audit_factory(console)(state) is None
    assert state.error == ""


def test_service_toggle_ui_domain_matches_boolean_runtime_contract():
    from rasai import console_provider_environment as facade
    from rasai.standards_console_runtime import install as install_standards_console_runtime

    install_standards_console_runtime()
    _repair_service_toggle_domains()

    spec = next(
        item for item in facade.refresh_specs()
        if item.name == "RASAI_GSC_ENABLED"
    )
    assert spec.value_type == "booleano"
    assert tuple(spec.accepted) == ("true", "false")


def test_search_capability_contains_serp_but_not_gsc_and_gsc_has_own_capability():
    from rasai import console_ui_catalog as catalog

    _install_search_capability_split()

    search_names = {item.name for item in catalog.capability_specs("search-intelligence")}
    gsc_names = {item.name for item in catalog.capability_specs("google-search-console")}
    observed_names = {item.name for item in catalog.capability_specs("observability")}

    assert "RASAI_SERP_MODE" in search_names
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" not in search_names
    assert "RASAI_GSC_ENABLED" not in search_names

    assert "RASAI_GSC_ENABLED" in gsc_names
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" in gsc_names
    assert "RASAI_SERP_MODE" not in gsc_names

    assert "RASAI_SERP_MODE" not in observed_names
    assert "RASAI_GSC_ENABLED" not in observed_names
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" not in observed_names

    labels = {item.key: item.label for item in catalog.CAPABILITIES}
    assert labels["search-intelligence"] == "Search Intelligence / SERP"
    assert labels["google-search-console"] == "Google Search Console"


def test_serp_configured_without_terms_is_not_requested(monkeypatch):
    monkeypatch.setenv("RASAI_SERP_MODE", "live")
    monkeypatch.setenv("RASAI_SERP_PROVIDER", "serpapi")
    monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "test-key")

    status, detail = _search_intelligence_status(SimpleNamespace(search_queries=()))

    assert status == "NÃO SOLICITADO"
    assert "provider serpapi configurado" in detail
    assert "nenhum termo SERP" in detail


def test_serp_explicit_disabled_remains_disabled(monkeypatch):
    monkeypatch.setenv("RASAI_SERP_MODE", "disabled")

    status, detail = _search_intelligence_status(SimpleNamespace(search_queries=()))

    assert status == "DESABILITADO"
    assert "RASAI_SERP_MODE=disabled" in detail


def test_gsc_auto_without_credentials_is_not_configured_not_serp_failure(monkeypatch):
    for name in (
        "RASAI_GSC_ENABLED",
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID",
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET",
        "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    status, detail = _gsc_status(SimpleNamespace(target="https://example.test/"))

    assert status == "NÃO CONFIGURADO"
    assert "GSC automático/opcional" in detail


def test_gsc_configured_and_covering_target_is_apt(monkeypatch):
    monkeypatch.delenv("RASAI_GSC_ENABLED", raising=False)
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "oauth-access-token")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", "sc-domain:example.test")
    for name in (
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID",
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET",
        "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    status, detail = _gsc_status(SimpleNamespace(target="https://www.example.test/page"))

    assert status == "APTO"
    assert "escopo cobre a URL" in detail

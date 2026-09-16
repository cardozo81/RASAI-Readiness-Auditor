from __future__ import annotations

from rasai.gsc_oauth_console import install as install_gsc_oauth_console
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_runtime import install_pre_context as install_standards_pre_context


# Compose the same Search/GSC metadata families used by the public local console.
install_standards_pre_context()
install_standards_console_runtime()
install_gsc_oauth_console()

from rasai import console_provider_environment as facade
from rasai import console_ui_catalog as ui_catalog
from rasai.console_search_configuration_groups import (
    GSC_CONFIGURATION_NAMES,
    context_label_for_name,
    install,
)
from rasai.console_search_owner_routing import install as install_owner_routing
from rasai.console_ui_catalog import catalog_specs
from rasai.search_intelligence.config import SERP_ENV_NAMES


install()
install_owner_routing()


def test_every_registered_configuration_is_reachable_from_all_configurations() -> None:
    registered = {spec.name for spec in facade.refresh_specs()}
    reachable = {spec.name for spec in catalog_specs("all")}
    assert reachable == registered


def test_complete_serp_and_gsc_operator_contracts_are_exposed() -> None:
    exposed = {spec.name for spec in facade.refresh_specs()}
    missing_serp = sorted(set(SERP_ENV_NAMES) - exposed)
    missing_gsc = sorted(set(GSC_CONFIGURATION_NAMES) - exposed)
    assert not missing_serp, "SERP settings hidden from console: " + ", ".join(missing_serp)
    assert not missing_gsc, "GSC settings hidden from console: " + ", ".join(missing_gsc)


def test_serp_configuration_is_split_by_operator_context() -> None:
    assert context_label_for_name("RASAI_SERP_MODE") == "SERP / Ativação e modo de coleta"
    assert context_label_for_name("RASAI_SERP_PROVIDER") == "SERP / Provider e credencial"
    assert context_label_for_name("RASAI_SERPAPI_API_KEY") == "SERP / Provider e credencial"
    assert context_label_for_name("RASAI_SERP_MAX_REQUESTS") == "SERP / Escopo e limites de coleta"
    assert context_label_for_name("RASAI_SERP_RETRIES") == "SERP / Rede, retries e ritmo"
    assert context_label_for_name("RASAI_SERP_FIXTURE_PATH") == "SERP / Fixture / teste offline"


def test_gsc_configuration_is_split_by_operator_context() -> None:
    assert context_label_for_name("RASAI_GSC_ENABLED") == "Google Search Console / Ativação"
    assert context_label_for_name("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN") == (
        "Google Search Console / OAuth temporário — teste/uso pontual"
    )
    assert context_label_for_name("RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID") == (
        "Google Search Console / OAuth durável — recomendado"
    )
    assert context_label_for_name("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL") == (
        "Google Search Console / Property e cobertura da URL auditada"
    )
    assert context_label_for_name("RASAI_GSC_SEARCH_MAX_ROWS") == (
        "Google Search Console / Search Analytics — janela e volume"
    )


def test_search_settings_are_owned_by_search_even_when_source_category_is_metrics() -> None:
    specs = {spec.name: spec for spec in facade.refresh_specs()}
    assert ui_catalog.owner_for(specs["RASAI_GSC_ENABLED"]).startswith(
        "Search / Google Search Console / Ativação"
    )
    assert ui_catalog.owner_for(specs["RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"]).startswith(
        "Search / Google Search Console / Property"
    )
    assert ui_catalog.owner_for(specs["RASAI_SERP_MODE"]).startswith(
        "Search / SERP / Ativação"
    )


def test_gsc_temporary_token_is_presented_as_alternative_not_parallel_requirement() -> None:
    spec = next(
        item
        for item in facade.refresh_specs()
        if item.name == "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"
    )
    normalized = facade.normalize_spec(spec)
    assert "OU" in normalized.required_when
    assert "Client ID" in normalized.required_when
    assert "tempor" in normalized.purpose.casefold()
    assert normalized.sensitive is True

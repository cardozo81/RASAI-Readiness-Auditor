"""Focused regression for issue #317; never performs billable HTTP requests."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from rasai.console_environment import _search_specs, _validate
from rasai.console_search_intelligence import SearchConsoleState, _explicit_brazil_scope
from rasai.console_settings import load_console_config, save_console_config
from rasai.search_intelligence.perplexity_request_policy import (
    OPTION_FIELDS, PREFIX, resolve_request_options, validate_request_options,
)


def test_baseline_is_unrestricted_without_explicit_serp_scope() -> None:
    result = resolve_request_options({})
    assert result == {"max_results": 10}
    assert "country" not in result
    assert "search_domain_filter" not in result
    assert "search_recency_filter" not in result


def test_brazil_audit_scope_precedes_integration_country() -> None:
    env = {
        PREFIX + "COUNTRY": "US",
        PREFIX + "MAX_RESULTS": "12",
    }
    result = resolve_request_options(
        env, explicit_brazil=_explicit_brazil_scope("São Paulo, SP, Brasil")
    )
    assert result["country"] == "BR"
    assert result["search_language_filter"] == ["pt"]
    assert result["max_results"] == 12
    # No forced .br and no implicit time filters even when the AUD is Brazilian.
    assert "search_domain_filter" not in result
    assert "search_recency_filter" not in result
    assert resolve_request_options(env)["country"] == "US"


def test_explicit_language_overrides_brazil_default() -> None:
    values = resolve_request_options(
        {PREFIX + "SEARCH_LANGUAGE_FILTER": "en,pt"},
        explicit_brazil=True,
    )
    assert values["country"] == "BR"
    assert values["search_language_filter"] == ["en", "pt"]


def test_opt_in_scope_allows_domains_dates_and_content_limits() -> None:
    values = resolve_request_options({
        PREFIX + "SEARCH_DOMAIN_FILTER": "example.com;portal.com.br;example.com",
        PREFIX + "SEARCH_RECENCY_FILTER": "year",
        PREFIX + "SEARCH_AFTER_DATE": "01/01/2025",
        PREFIX + "LAST_UPDATED_BEFORE": "12/31/2026",
        PREFIX + "MAX_TOKENS": "10000",
        PREFIX + "MAX_TOKENS_PER_PAGE": "3000",
    })
    assert values["search_domain_filter"] == ["example.com", "portal.com.br"]
    assert values["search_recency_filter"] == "year"
    assert values["search_after_date_filter"] == "01/01/2025"
    assert values["last_updated_before_filter"] == "12/31/2026"
    assert values["max_tokens"] == 10000
    assert values["max_tokens_per_page"] == 3000


@pytest.mark.parametrize("env", [
    {PREFIX + "MAX_RESULTS": "21"},
    {PREFIX + "MAX_RESULTS": "0"},
    {PREFIX + "MAX_RESULTS": "NaN"},
    {PREFIX + "COUNTRY": "Brazil"},
    {PREFIX + "SEARCH_LANGUAGE_FILTER": "pt-BR"},
    {PREFIX + "SEARCH_DOMAIN_FILTER": "https://example.com/path"},
    {PREFIX + "SEARCH_DOMAIN_FILTER": "*.example.com"},
    {PREFIX + "SEARCH_RECENCY_FILTER": "forever"},
    {PREFIX + "SEARCH_AFTER_DATE": "02/30/2026"},
    {PREFIX + "SEARCH_AFTER_DATE": "2026-10-08"},
    {PREFIX + "SEARCH_AFTER_DATE": "12/31/2026", PREFIX + "SEARCH_BEFORE_DATE": "01/01/2026"},
    {PREFIX + "MAX_TOKENS_PER_PAGE": "-1"},
])
def test_invalid_configuration_rejected_before_network(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        resolve_request_options(env)


def test_outbound_validator_does_not_accept_arbitrary_fields() -> None:
    with pytest.raises(ValueError, match="desconhecido"):
        validate_request_options({"api_key": "DO_NOT_SEND"})
    with pytest.raises(ValueError):
        validate_request_options({"max_results": 30}, search_type="web")


def test_editor_and_request_use_same_policy() -> None:
    assert _validate(PREFIX + "COUNTRY", "br") == "BR"
    assert _validate(PREFIX + "SEARCH_LANGUAGE_FILTER", "PT, en") == "pt,en"
    assert _validate(PREFIX + "SEARCH_DOMAIN_FILTER", "Example.COM") == "example.com"
    assert _validate(PREFIX + "SEARCH_RECENCY_FILTER", "Year") == "year"
    assert _validate(PREFIX + "MAX_RESULTS", "7") == "7"
    with pytest.raises(ValueError):
        _validate(PREFIX + "SEARCH_DOMAIN_FILTER", "ftp://example.com")


def test_every_scope_variable_is_canonical_nonsecret_and_persistible() -> None:
    specs = {spec.name: spec for spec in _search_specs()}
    for suffix in OPTION_FIELDS:
        name = PREFIX + suffix
        assert name in specs
        assert specs[name].sensitive is False
    assert specs[PREFIX + "MAX_RESULTS"].default == "10"


def test_explicit_options_survive_restart_without_secret_in_ini() -> None:
    with TemporaryDirectory() as temp, patch.dict(os.environ, {
        PREFIX + "SEARCH_DOMAIN_FILTER": "example.com",
        PREFIX + "MAX_RESULTS": "7",
        "PERPLEXITY_API_KEY": "NEVER_PERSIST_KEY_317",
    }, clear=True):
        path = Path(temp) / "rasai-console.ini"
        save_console_config(SearchConsoleState(), path)
        body = path.read_text(encoding="utf-8")
        assert "NEVER_PERSIST_KEY_317" not in body
        assert PREFIX + "MAX_RESULTS = 7" in body
        assert PREFIX + "SEARCH_DOMAIN_FILTER = example.com" in body
        os.environ.pop(PREFIX + "MAX_RESULTS")
        os.environ.pop(PREFIX + "SEARCH_DOMAIN_FILTER")
        outcome = load_console_config(SearchConsoleState(), path)
        assert outcome.warnings == ()
        assert os.environ[PREFIX + "MAX_RESULTS"] == "7"
        assert os.environ[PREFIX + "SEARCH_DOMAIN_FILTER"] == "example.com"

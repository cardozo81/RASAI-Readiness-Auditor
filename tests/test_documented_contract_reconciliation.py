from __future__ import annotations

import os

import pytest

from rasai.documented_contract_reconciliation import (
    AUTO_EXCLUDE_ENV,
    _CURRENT_PSI_CATEGORIES,
    _install_auto_runtime_filter,
    _install_console_auto_capability_filter,
    _install_current_pagespeed_categories,
    parse_auto_exclusions,
)


def test_auto_exclusion_is_canonical_and_does_not_remove_key(monkeypatch) -> None:
    from rasai import console_config, provider_runtime_policy

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.setenv(AUTO_EXCLUDE_ENV, "openai")
    original_key = os.environ["OPENAI_API_KEY"]

    _install_auto_runtime_filter()
    _install_console_auto_capability_filter()

    assert parse_auto_exclusions() == ("openai",)
    capabilities = console_config.provider_capabilities()
    assert capabilities["openai"].available is True
    assert capabilities["auto"].available is True
    assert "OPENAI" not in capabilities["auto"].reason.split("pool AUTO", 1)[-1].split(";", 1)[0]
    assert os.environ["OPENAI_API_KEY"] == original_key

    routed = provider_runtime_policy.build_semantic_provider("auto")
    assert "OPENAI" not in [item.name for item in routed.providers]
    assert "OPENAI:USER_EXCLUDED_FROM_AUTO" in routed.excluded_configurations

    explicit = provider_runtime_policy.build_semantic_provider("openai")
    assert explicit.name == "OPENAI"
    assert os.environ["OPENAI_API_KEY"] == original_key


def test_auto_exclusion_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        parse_auto_exclusions("does-not-exist")


def test_current_pagespeed_contract_accepts_agentic_and_defaults_to_it(monkeypatch) -> None:
    from rasai import cli, m21_web_performance

    monkeypatch.delenv("RASAI_LIGHTHOUSE_CATEGORIES", raising=False)
    _install_current_pagespeed_categories()
    config = m21_web_performance.WebPerformanceConfig(enabled=True).validate()
    assert config.categories == _CURRENT_PSI_CATEGORIES
    assert cli._configured_lighthouse_categories(None) == _CURRENT_PSI_CATEGORIES
    explicit = m21_web_performance.WebPerformanceConfig(
        enabled=True,
        categories=("agentic-browsing",),
    ).validate()
    assert explicit.categories == ("agentic-browsing",)

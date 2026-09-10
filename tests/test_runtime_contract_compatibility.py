from __future__ import annotations


def test_public_runtime_composition_skips_contracts_that_are_native(monkeypatch) -> None:
    from rasai import documented_contract_reconciliation as legacy
    from rasai import runtime_contract_compatibility as composition

    calls: list[str] = []
    expected = (
        "_install_ai_cost_report_fix",
        "_install_ai_usage_presentation_fix",
        "_install_scoring_wording_fix",
        "_install_crawling_capture_wording_fix",
        "_install_search_comparison_guidance",
        "_install_m24_fallback_telemetry_fix",
    )

    for name in expected:
        monkeypatch.setattr(
            legacy,
            name,
            lambda name=name: calls.append(name),
        )

    def obsolete() -> None:
        raise AssertionError("native contract must not be reinstalled by the public runtime")

    for name in (
        "_install_auto_runtime_filter",
        "_install_console_auto_persistence",
        "_install_current_pagespeed_categories",
    ):
        monkeypatch.setattr(legacy, name, obsolete)

    composition._RUNTIME_INSTALLED = False
    composition.install_runtime_contract_compatibility()

    assert tuple(calls) == expected


def test_console_composition_keeps_only_console_specific_adapters(monkeypatch) -> None:
    from rasai import documented_contract_reconciliation as legacy
    from rasai import runtime_contract_compatibility as composition

    calls: list[str] = []
    expected = (
        "_install_console_auto_capability_filter",
        "_install_console_ai_selector",
        "_install_console_search_content_comparison",
    )
    for name in expected:
        monkeypatch.setattr(
            legacy,
            name,
            lambda name=name: calls.append(name),
        )

    composition._RUNTIME_INSTALLED = True
    composition._CONSOLE_INSTALLED = False
    composition.install_console_runtime_contract_compatibility()

    assert tuple(calls) == expected


def test_auto_exclusion_is_native_to_provider_runtime_policy() -> None:
    from rasai import provider_runtime_policy

    env = {
        "OPENAI_API_KEY": "sk-test-openai",
        "DEEPSEEK_API_KEY": "test-deepseek",
        provider_runtime_policy.AUTO_EXCLUDE_ENV: "openai",
    }
    routed = provider_runtime_policy.build_semantic_provider("auto", env=env)

    assert "OPENAI" not in [provider.name for provider in routed.providers]
    assert "DEEPSEEK" in [provider.name for provider in routed.providers]
    assert "OPENAI:USER_EXCLUDED_FROM_AUTO" in routed.excluded_configurations
    assert env["OPENAI_API_KEY"] == "sk-test-openai"


def test_agentic_pagespeed_default_is_native() -> None:
    from rasai import m21_web_performance

    config = m21_web_performance.WebPerformanceConfig(enabled=True).validate()
    assert config.categories == (
        "performance",
        "accessibility",
        "best-practices",
        "seo",
        "agentic-browsing",
    )

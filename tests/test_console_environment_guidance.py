from __future__ import annotations

import os

import pytest

from rasai.console_environment import CATEGORIES, ENV_NAMES, SPEC_BY_NAME, SPECS, _validate
from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX


def test_every_exposed_environment_variable_has_one_spec() -> None:
    assert len(SPECS) == len(ENV_NAMES)
    assert {spec.name for spec in SPECS} == set(ENV_NAMES)
    assert len({spec.name for spec in SPECS}) == len(SPECS)
    assert all(spec.purpose and spec.value_type and spec.required_when and spec.impact for spec in SPECS)


def test_categories_cover_all_specs_and_are_not_empty() -> None:
    assert all(any(spec.category == category for spec in SPECS) for category in CATEGORIES)
    assert {spec.category for spec in SPECS} == set(CATEGORIES)
    for required in (
        "IA - contexto editorial / YMYL",
        "Synthetic Apdex",
        "Search Intelligence / Observability",
        "Control plane / SaaS",
        "Web API / Identity",
        "Remote control plane",
    ):
        assert required in CATEGORIES


def test_known_domains_and_effective_defaults_are_exposed() -> None:
    device = SPEC_BY_NAME["RASAI_DEVICE_CONTEXT"]
    assert device.accepted == ("mobile", "desktop", "both")
    assert device.default == "mobile"

    field = SPEC_BY_NAME["RASAI_WEB_PERFORMANCE_FIELD_SOURCE"]
    assert field.accepted == ("auto", "pagespeed", "crux", "none")
    assert field.default == "auto"

    concurrency = SPEC_BY_NAME["RASAI_APDEX_CONCURRENCY"]
    assert concurrency.accepted == ("1", "2")
    assert concurrency.default == "1"

    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE"].default == "false"
    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"].default == DEFAULT_UX_DEVICE_MIX
    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT"].default == "true"

    risk = SPEC_BY_NAME["RASAI_CONTENT_RISK_PROFILE"]
    assert risk.accepted == ("auto", "standard", "ymyl")
    assert risk.default == "auto"
    assert risk.category == "IA - contexto editorial / YMYL"

    ymyl = SPEC_BY_NAME["RASAI_YMYL_CATEGORY"]
    assert "financial-security" in ymyl.accepted
    assert ymyl.default == "auto"

    assert SPEC_BY_NAME["RASAI_PAGE_PURPOSE"].default == "auto"
    assert SPEC_BY_NAME["RASAI_INTENDED_AUDIENCE"].default == "auto"
    assert SPEC_BY_NAME["RASAI_EXPERIENCE_REQUIREMENT"].default == "auto"
    assert SPEC_BY_NAME["RASAI_FRESHNESS_SENSITIVITY"].default == "auto"
    assert SPEC_BY_NAME["RASAI_CONTENT_ORIGIN"].default == "auto"

    assert SPEC_BY_NAME["RASAI_SERP_MODE"].default == "disabled"
    assert SPEC_BY_NAME["RASAI_SERP_PROVIDER"].default == "serpapi"
    assert SPEC_BY_NAME["RASAI_PLATFORM_DB_BACKEND"].default == "sqlite"
    assert SPEC_BY_NAME["RASAI_API_AUTH_MODE"].default == "deny"
    assert SPEC_BY_NAME["RASAI_API_AUDITS_ROOT"].default == "audits"
    assert SPEC_BY_NAME["RASAI_REMOTE_TIMEOUT_SECONDS"].default == "30"

    assert SPEC_BY_NAME["OPENAI_API_KEY"].sensitive is True
    assert SPEC_BY_NAME["RASAI_PLATFORM_DATABASE_URL"].sensitive is True
    assert SPEC_BY_NAME["RASAI_OIDC_SESSION_SECRET"].sensitive is True
    assert SPEC_BY_NAME["DYNATRACE_API_TOKEN"].sensitive is True
    assert SPEC_BY_NAME["RASAI_OPENAI_MODEL"].default == "gpt-5.6-luna"
    assert SPEC_BY_NAME["RASAI_OPENAI_REASONING_EFFORT"].default == "NONE"
    assert "RASAI_QWEN_REASONING_EFFORT" not in SPEC_BY_NAME


def test_additional_console_validation_rejects_invalid_values(tmp_path) -> None:
    with pytest.raises(ValueError):
        _validate("RASAI_LOG_LEVEL", "verbose")
    assert _validate("RASAI_LOG_LEVEL", "debug") == "DEBUG"

    with pytest.raises(ValueError):
        _validate("RASAI_LIGHTHOUSE_CATEGORIES", "performance,unknown")
    with pytest.raises(ValueError):
        _validate("RASAI_LIGHTHOUSE_CATEGORIES", "seo,seo")
    assert _validate("RASAI_LIGHTHOUSE_CATEGORIES", "performance, seo") == "performance,seo"

    with pytest.raises(ValueError):
        _validate("RASAI_XAI_ENDPOINT", "not-a-url")
    assert _validate("RASAI_XAI_ENDPOINT", "https://example.test/v1/responses") == "https://example.test/v1/responses"

    assert _validate("RASAI_CONTENT_RISK_PROFILE", "YMYL") == "ymyl"
    assert _validate("RASAI_YMYL_CATEGORY", "financial-security") == "financial-security"
    with pytest.raises(ValueError):
        _validate("RASAI_CONTENT_RISK_PROFILE", "critical")

    assert _validate(
        "RASAI_APDEX_EXPERIENCE_DEVICE_MIX",
        "mobile=60,desktop=35,tablet=5",
    ) == "mobile=60,desktop=35,tablet=5"
    with pytest.raises(ValueError):
        _validate("RASAI_APDEX_EXPERIENCE_DEVICE_MIX", "mobile=60,desktop=30")

    assert _validate("RASAI_SERP_MODE", "LIVE") == "live"
    with pytest.raises(ValueError):
        _validate("RASAI_SERP_MAX_REQUESTS", "0")

    assert _validate("RASAI_API_AUTH_MODE", "OIDC") == "oidc"
    with pytest.raises(ValueError):
        _validate("RASAI_OIDC_SESSION_TTL_SECONDS", "60")

    with pytest.raises(ValueError):
        _validate("RASAI_CONFIG", str(tmp_path / "missing.toml"))
    config = tmp_path / "rasai.toml"
    config.write_text("[rasai]\nlog_level='INFO'\n", encoding="utf-8")
    assert _validate("RASAI_CONFIG", str(config)) == str(config)


def test_defaults_do_not_require_materializing_environment(monkeypatch) -> None:
    for name in (
        "RASAI_DEVICE_CONTEXT",
        "RASAI_AI_TIMEOUT_SECONDS",
        "RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS",
        "RASAI_CONTENT_RISK_PROFILE",
        "RASAI_APDEX_EXPERIENCE_DEVICE_MIX",
    ):
        monkeypatch.delenv(name, raising=False)
    assert SPEC_BY_NAME["RASAI_DEVICE_CONTEXT"].default == "mobile"
    assert SPEC_BY_NAME["RASAI_AI_TIMEOUT_SECONDS"].default == "180"
    assert SPEC_BY_NAME["RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS"].default == "120"
    assert SPEC_BY_NAME["RASAI_CONTENT_RISK_PROFILE"].default == "auto"
    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"].default == DEFAULT_UX_DEVICE_MIX
    assert "RASAI_DEVICE_CONTEXT" not in os.environ

from __future__ import annotations

import os

import pytest

from searchgeo.console_environment import CATEGORIES, ENV_NAMES, SPEC_BY_NAME, SPECS, _validate


def test_every_exposed_environment_variable_has_one_spec() -> None:
    assert len(ENV_NAMES) == 52
    assert len(SPECS) == len(ENV_NAMES)
    assert {spec.name for spec in SPECS} == set(ENV_NAMES)
    assert len({spec.name for spec in SPECS}) == len(SPECS)
    assert all(spec.purpose and spec.value_type and spec.required_when and spec.impact for spec in SPECS)


def test_categories_cover_all_specs_and_are_not_empty() -> None:
    assert all(any(spec.category == category for spec in SPECS) for category in CATEGORIES)
    assert {spec.category for spec in SPECS} == set(CATEGORIES)
    assert "IA — contexto editorial / YMYL" in CATEGORIES


def test_known_domains_and_effective_defaults_are_exposed() -> None:
    device = SPEC_BY_NAME["SEARCHGEO_DEVICE_CONTEXT"]
    assert device.accepted == ("mobile", "desktop", "both")
    assert device.default == "mobile"

    field = SPEC_BY_NAME["SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE"]
    assert field.accepted == ("auto", "pagespeed", "crux", "none")
    assert field.default == "auto"

    concurrency = SPEC_BY_NAME["SEARCHGEO_APDEX_CONCURRENCY"]
    assert concurrency.accepted == ("1", "2")
    assert concurrency.default == "1"

    risk = SPEC_BY_NAME["SEARCHGEO_CONTENT_RISK_PROFILE"]
    assert risk.accepted == ("auto", "standard", "ymyl")
    assert risk.default == "auto"
    assert risk.category == "IA — contexto editorial / YMYL"

    ymyl = SPEC_BY_NAME["SEARCHGEO_YMYL_CATEGORY"]
    assert "financial-security" in ymyl.accepted
    assert ymyl.default == "auto"

    assert SPEC_BY_NAME["SEARCHGEO_PAGE_PURPOSE"].default == "auto"
    assert SPEC_BY_NAME["SEARCHGEO_INTENDED_AUDIENCE"].default == "auto"
    assert SPEC_BY_NAME["SEARCHGEO_EXPERIENCE_REQUIREMENT"].default == "auto"
    assert SPEC_BY_NAME["SEARCHGEO_FRESHNESS_SENSITIVITY"].default == "auto"
    assert SPEC_BY_NAME["SEARCHGEO_CONTENT_ORIGIN"].default == "auto"

    assert SPEC_BY_NAME["OPENAI_API_KEY"].sensitive is True
    assert SPEC_BY_NAME["SEARCHGEO_OPENAI_MODEL"].default == "gpt-5.6-luna"
    assert SPEC_BY_NAME["SEARCHGEO_OPENAI_REASONING_EFFORT"].default == "NONE"
    assert "SEARCHGEO_QWEN_REASONING_EFFORT" not in SPEC_BY_NAME


def test_additional_console_validation_rejects_invalid_values(tmp_path) -> None:
    with pytest.raises(ValueError):
        _validate("SEARCHGEO_LOG_LEVEL", "verbose")
    assert _validate("SEARCHGEO_LOG_LEVEL", "debug") == "DEBUG"

    with pytest.raises(ValueError):
        _validate("SEARCHGEO_LIGHTHOUSE_CATEGORIES", "performance,unknown")
    with pytest.raises(ValueError):
        _validate("SEARCHGEO_LIGHTHOUSE_CATEGORIES", "seo,seo")
    assert _validate("SEARCHGEO_LIGHTHOUSE_CATEGORIES", "performance, seo") == "performance,seo"

    with pytest.raises(ValueError):
        _validate("SEARCHGEO_XAI_ENDPOINT", "not-a-url")
    assert _validate("SEARCHGEO_XAI_ENDPOINT", "https://example.test/v1/responses") == "https://example.test/v1/responses"

    assert _validate("SEARCHGEO_CONTENT_RISK_PROFILE", "YMYL") == "ymyl"
    assert _validate("SEARCHGEO_YMYL_CATEGORY", "financial-security") == "financial-security"
    with pytest.raises(ValueError):
        _validate("SEARCHGEO_CONTENT_RISK_PROFILE", "critical")

    with pytest.raises(ValueError):
        _validate("SEARCHGEO_CONFIG", str(tmp_path / "missing.toml"))
    config = tmp_path / "searchgeo.toml"
    config.write_text("[searchgeo]\nlog_level='INFO'\n", encoding="utf-8")
    assert _validate("SEARCHGEO_CONFIG", str(config)) == str(config)


def test_defaults_do_not_require_materializing_environment(monkeypatch) -> None:
    monkeypatch.delenv("SEARCHGEO_DEVICE_CONTEXT", raising=False)
    monkeypatch.delenv("SEARCHGEO_AI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SEARCHGEO_CONTENT_RISK_PROFILE", raising=False)
    assert SPEC_BY_NAME["SEARCHGEO_DEVICE_CONTEXT"].default == "mobile"
    assert SPEC_BY_NAME["SEARCHGEO_AI_TIMEOUT_SECONDS"].default == "180"
    assert SPEC_BY_NAME["SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS"].default == "120"
    assert SPEC_BY_NAME["SEARCHGEO_CONTENT_RISK_PROFILE"].default == "auto"
    assert "SEARCHGEO_DEVICE_CONTEXT" not in os.environ

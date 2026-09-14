from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai import console_execution_profiles as profiles
from rasai.console_execution_profile_readiness import (
    GSC_PROFILE_REQUIRED,
    _candidate,
    install as install_profile_readiness,
    profile_status,
    set_gsc_profile_policy,
)
from rasai.gsc_scope import (
    GSC_ENABLED_ENV,
    GSC_SITE_URL_ENV,
    GSC_TOKEN_ENV,
    STATE_PROPERTY_URL_MISMATCH,
    assess_gsc_target,
    gsc_property_covers_url,
)
from rasai.gsc_scope_runtime import _scope_mismatch_result


def _state(target: str = "https://www.portoseguro.com.br/") -> SimpleNamespace:
    return SimpleNamespace(
        input_mode="url",
        target=target,
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
        web_performance=False,
        lighthouse_categories="",
        content_remediation=False,
        technical_remediation=False,
        synthetic_apdex=False,
        apdex_experience=False,
        search_queries=(),
        search_depth=20,
        search_device="mobile",
        improvement_enabled=False,
        improvement_provider="",
        improvement_model="",
        improvement_reasoning="",
        error="",
        operation="",
    )


def test_sc_domain_property_covers_domain_and_subdomains_only() -> None:
    assert gsc_property_covers_url("sc-domain:example.com", "https://example.com/") is True
    assert gsc_property_covers_url("sc-domain:example.com", "https://www.example.com/path") is True
    assert gsc_property_covers_url("sc-domain:example.com", "https://example.net/") is False


def test_url_prefix_property_is_protocol_host_and_path_specific() -> None:
    property_url = "https://www.example.com/blog/"
    assert gsc_property_covers_url(property_url, "https://www.example.com/blog/post-1") is True
    assert gsc_property_covers_url(property_url, "http://www.example.com/blog/post-1") is False
    assert gsc_property_covers_url(property_url, "https://example.com/blog/post-1") is False
    assert gsc_property_covers_url(property_url, "https://www.example.com/produtos/") is False


def test_auto_mismatch_is_non_blocking_but_required_mismatch_blocks() -> None:
    env = {
        GSC_TOKEN_ENV: "oauth-token",
        GSC_SITE_URL_ENV: "sc-domain:sersolucao.com.br",
    }
    automatic = assess_gsc_target("https://www.portoseguro.com.br/", env)
    assert automatic.state == STATE_PROPERTY_URL_MISMATCH
    assert automatic.blocking is False
    assert "não será requisito" in automatic.message

    required = assess_gsc_target(
        "https://www.portoseguro.com.br/",
        {**env, GSC_ENABLED_ENV: "true"},
    )
    assert required.state == STATE_PROPERTY_URL_MISMATCH
    assert required.blocking is True
    assert "não poderá atingir" in required.message


def test_profile_defaults_to_gsc_if_compatible_and_required_policy_surfaces_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GSC_TOKEN_ENV, "oauth-token")
    monkeypatch.setenv(GSC_SITE_URL_ENV, "sc-domain:sersolucao.com.br")
    monkeypatch.delenv(GSC_ENABLED_ENV, raising=False)
    install_profile_readiness()
    state = _state()

    ready, blockers, advisories = profile_status(state, "seo")
    assert ready is True
    assert not any("Google Search Console" in item for item in blockers)
    assert any("não cobre" in item for item in advisories if item.startswith("GSC"))

    definition = profiles._PROFILE_BY_ID["seo"]
    candidate = _candidate(state, definition)
    set_gsc_profile_policy(candidate, GSC_PROFILE_REQUIRED)
    ready, blockers, _ = profiles.dependency_status(state, candidate)
    assert ready is False
    assert any("Google Search Console" in item and "não cobre" in item for item in blockers)


def test_required_scope_mismatch_result_is_configuration_failure() -> None:
    state_info = {
        "requested": True,
        "configured": True,
        "effective_enabled": True,
        "configuration_source": "EXPLICIT",
    }
    result = _scope_mismatch_result(
        state_info=state_info,
        site_url="sc-domain:sersolucao.com.br",
        urls=("https://www.portoseguro.com.br/",),
        mode="required",
        mismatched=("https://www.portoseguro.com.br/",),
    )
    assert result["collection_state"] == STATE_PROPERTY_URL_MISMATCH
    assert result["effective_enabled"] is True
    assert result["targets_attempted"] == 0
    assert "parcial/não final" in result["reason"]


def test_auto_scope_mismatch_is_not_applicable_without_provider_call() -> None:
    state_info = {
        "requested": True,
        "configured": True,
        "effective_enabled": True,
        "configuration_source": "CREDENTIAL_DRIVEN_DEFAULT",
    }
    result = _scope_mismatch_result(
        state_info=state_info,
        site_url="sc-domain:sersolucao.com.br",
        urls=("https://www.portoseguro.com.br/",),
        mode="auto",
        mismatched=("https://www.portoseguro.com.br/",),
    )
    assert result["collection_state"] == "NOT_APPLICABLE"
    assert result["effective_enabled"] is False
    assert result["errors"] == []

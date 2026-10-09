"""#355: Dynatrace RUM configuration is not RASAi's homologated synthetic Apdex."""
from __future__ import annotations

from copy import deepcopy

import pytest

from rasai.dynatrace_apdex_arch_advisory_355 import (
    assess_dynatrace_apdex_architecture as assess,
)


def _thresholds():
    return {
        "toleratedThresholdSeconds": 2.0,
        "frustratingThresholdSeconds": 8.0,
    }


def _fallback():
    return {
        "toleratedFallbackThresholdSeconds": 3.0,
        "frustratingFallbackThresholdSeconds": 12.0,
    }


def _config(*, xhr=False, count=None, capture=None):
    result = {
        "load_actions": {
            "kpm": "VISUALLY_COMPLETE",
            "thresholds": _thresholds(),
            "fallbackThresholds": _fallback(),
        },
    }
    if xhr:
        result["xhr_actions"] = {
            "kpm": "USER_ACTION_DURATION",
            "thresholds": _thresholds(),
            "fallbackThresholds": _fallback(),
        }
    if count is not None:
        result["action_counts"] = {"load": 12, "xhr": count}
    if capture is not None:
        result["capture"] = capture
    return result


def _assess(architecture="CSR_SPA", **changes):
    args = {
        "architecture": architecture,
        "architecture_evidence_id": "ARCH-EV-1",
        "soft_navigation_observed": True,
        "async_requests_observed": True,
        "settings": _config(),
    }
    args.update(changes)
    return assess(**args)


def test_spa_load_only_does_not_imply_xhr_present_or_apdex_incorrect():
    outcome = _assess()
    assert outcome["status"] == "INSUFFICIENT_ACTION_SCOPE"
    assert outcome["reasons"] == ["XHR_APDEX_CONFIGURATION_NOT_PROVIDED"]
    assert outcome["observed_kpm"]["load_actions"] == "VISUALLY_COMPLETE"
    assert outcome["recommended_numeric_thresholds"] is None
    assert outcome["new_apdex_score"] is None
    assert outcome["dynatrace_provider_requests"] == outcome["audit_writes"] == 0
    assert outcome["synthetic_m23_m25_changed"] is False


def test_spa_observed_async_route_with_capture_disabled_requests_review():
    value = _assess(settings=_config(
        xhr=True, count=0, capture={"xhr": False, "fetch": False},
    ))
    assert value["status"] == "REVIEW_RECOMMENDED"
    assert "ASYNC_CAPTURE_DISABLED_FOR_OBSERVED_SOFT_NAVIGATION" in value["reasons"]
    assert "fallbackThresholds" in value["review_actions"][0]


def test_spa_xhr_configured_but_zero_recorded_actions_requests_review():
    outcome = _assess(settings=_config(
        xhr=True, count=0, capture={"xhr": True, "fetch": True},
    ))
    assert outcome["status"] == "REVIEW_RECOMMENDED"
    assert outcome["reasons"] == ["NO_XHR_ACTIONS_IN_DECLARED_RUM_POPULATION"]


def test_spa_positive_xhr_population_can_be_plausible_without_proving_content_ready():
    snapshot = _config(
        xhr=True, count=14, capture={"xhr": True, "fetch": True},
    )
    outcome = _assess(settings=snapshot)
    assert outcome["status"] == "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE"
    assert outcome["reasons"] == []
    assert outcome["observed_kpm"] == {
        "load_actions": "VISUALLY_COMPLETE",
        "xhr_actions": "USER_ACTION_DURATION",
    }
    assert outcome["measurement_in_same_browser_sample_proven"] is False
    assert outcome["new_apdex_score"] is None


def test_xhr_configuration_alone_does_not_prove_rum_action_population():
    outcome = _assess(settings=_config(xhr=True))
    assert outcome["status"] == "INSUFFICIENT_ACTION_SCOPE"
    assert outcome["reasons"] == ["XHR_ACTION_POPULATION_NOT_PROVEN"]


def test_ssr_full_document_load_does_not_require_spa_xhr_settings():
    outcome = _assess(
        architecture="STATIC_OR_SSR",
        soft_navigation_observed=False,
        async_requests_observed=False,
    )
    assert outcome["status"] == "CONFIGURATION_PLAUSIBLE_FOR_DOCUMENT_NAVIGATION"
    assert outcome["reasons"] == []


def test_hydrated_and_mixed_need_observed_route_before_soft_action_advice():
    for architecture in ("HYDRATED", "MIXED"):
        result = _assess(
            architecture=architecture,
            soft_navigation_observed=None,
        )
        assert result["status"] == "INSUFFICIENT_ACTION_SCOPE"
        assert result["reasons"] == ["SOFT_NAVIGATION_NOT_PROVEN"]
        assert result["new_apdex_score"] is None


def test_no_async_soft_navigation_does_not_guess_xhr():
    result = _assess(async_requests_observed=False)
    assert result["status"] == "INSUFFICIENT_ACTION_SCOPE"
    assert result["reasons"] == ["ASYNC_TRIGGER_FOR_SOFT_NAVIGATION_NOT_PROVEN"]
    assert "customizada" in result["review_actions"][0]


@pytest.mark.parametrize("architecture", ["UNKNOWN", "INVALID", "", None])
def test_unknown_architecture_abstains_even_with_full_settings(architecture):
    result = _assess(
        architecture=architecture,
        settings=_config(xhr=True, count=50),
    )
    assert result["status"] == "NOT_EVALUABLE"
    assert "ARCHITECTURE_NOT_PROVEN" in result["reasons"]


def test_missing_dyna_settings_or_provenance_never_fabricates_configuration():
    a = _assess(settings=None)
    b = _assess(architecture_evidence_id=None)
    assert a["status"] == "NOT_EVALUABLE"
    assert a["observed_kpm"] == {}
    assert b["status"] == "NOT_EVALUABLE"
    assert b["reasons"] == ["ARCHITECTURE_EVIDENCE_NOT_VERIFIED"]


def test_wrong_metric_per_action_type_and_thresholds_fail_closed():
    config = _config(xhr=True)
    config["xhr_actions"]["kpm"] = "SPEED_INDEX"  # only load supports this
    result = _assess(settings=config)
    assert result["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert "xhr_actions:KPM_NOT_SUPPORTED_FOR_ACTION_TYPE" in result["reasons"]
    assert result["observed_kpm"] == {}

    config = _config()
    config["load_actions"]["fallbackThresholds"]["frustratingFallbackThresholdSeconds"] = 1
    result = _assess(settings=config)
    assert result["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert "load_actions:INVALID_FALLBACK_THRESHOLDS" in result["reasons"]


@pytest.mark.parametrize("bad", [
    {"toleratedThresholdSeconds": True, "frustratingThresholdSeconds": 8},
    {"toleratedThresholdSeconds": -1, "frustratingThresholdSeconds": 8},
    {"toleratedThresholdSeconds": 4, "frustratingThresholdSeconds": 4},
    {"toleratedThresholdSeconds": float("nan"), "frustratingThresholdSeconds": 8},
])
def test_invalid_thresholds_do_not_create_recommendations(bad):
    config = _config()
    config["load_actions"]["thresholds"] = bad
    result = _assess(settings=config)
    assert result["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert result["recommended_numeric_thresholds"] is None
    assert result["review_actions"] == []


def test_custom_actions_only_allow_user_action_duration():
    good = _config()
    good["custom_actions"] = {
        "kpm": "USER_ACTION_DURATION", "thresholds": _thresholds(),
    }
    assert _assess(settings=good)["status"] != "INVALID_SETTINGS_SNAPSHOT"
    bad = deepcopy(good)
    bad["custom_actions"]["kpm"] = "VISUALLY_COMPLETE"
    result = _assess(settings=bad)
    assert result["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert "custom_actions:KPM_NOT_SUPPORTED_FOR_ACTION_TYPE" in result["reasons"]


def test_no_homologated_apdex_runtime_dependency():
    from rasai import dynatrace_apdex_arch_advisory_355 as module
    assert not any(name in module.__dict__ for name in (
        "m23_apdex", "m25_apdex_experience", "requests", "httpx",
        "sqlite3", "AuditWorkspace", "build_provider",
    ))

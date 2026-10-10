"""#355: Dynatrace RUM configuration is not RASAi's homologated synthetic Apdex."""
from __future__ import annotations

from copy import deepcopy
import json

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

def test_offline_dynatrace_apdex_cli_uses_operator_json_without_runtime_bootstrap(
    tmp_path, monkeypatch, capsys,
):
    from rasai import entrypoint
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("offline advisory must not install collectors/providers"),
    )
    # This is operator-supplied data, not authenticated settings.read evidence.
    import json
    path = tmp_path / "dynatrace-export.json"
    config = _config(xhr=True, count=0, capture={"xhr": False, "fetch": False})
    config["api_token"] = "SENSITIVE_NEVER_PRINT"
    path.write_text(json.dumps(config), encoding="utf-8")
    before = path.read_bytes()
    assert entrypoint.main([
        "dynatrace-apdex-review",
        "--architecture", "CSR_SPA",
        "--architecture-evidence-id", "M6-OPERATOR-REFERENCE",
        "--soft-navigation", "observed",
        "--async-requests", "observed",
        "--settings-json", str(path),
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "REVIEW_RECOMMENDED"
    assert "ASYNC_CAPTURE_DISABLED_FOR_OBSERVED_SOFT_NAVIGATION" in response["reasons"]
    assert response["settings_provenance"] == "NOT_VERIFIED_BY_RASAI"
    assert response["actual_dynatrace_tenant_consulted"] is False
    assert response["dynatrace_provider_requests"] == response["audit_writes"] == 0
    assert response["rasai_synthetic_apdex_unchanged"] is True
    assert "SENSITIVE_NEVER_PRINT" not in json.dumps(response)
    assert path.read_bytes() == before


def test_offline_dynatrace_apdex_cli_absent_settings_fail_closed(tmp_path, capsys):
    from rasai.dynatrace_apdex_review_cli_355 import main
    import json
    assert main([
        "--architecture", "STATIC_OR_SSR",
        "--architecture-evidence-id", "M6-REFERENCE",
        "--soft-navigation", "not-observed",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "NOT_EVALUABLE"
    assert result["reasons"] == ["NO_DYNATRACE_SETTINGS_SNAPSHOT"]
    assert result["input_source"] == "NO_SETTINGS"
    assert result["dynatrace_provider_requests"] == 0
    with pytest.raises(SystemExit) as failed:
        main([
            "--architecture", "CSR_SPA", "--settings-json",
            str(tmp_path / "not-found.json"),
        ])
    assert failed.value.code == 2
    assert not (tmp_path / "not-found.json").exists()


def _effective_values_export():
    return {
        "items": [
            {
                "schemaId": "builtin:rum.web.key-performance-metric-load-actions",
                "schemaVersion": "1.1.0",
                "origin": "APPLICATION-TEST",
                "value": {
                    "kpm": "USER_ACTION_DURATION",
                    "thresholds": {
                        "toleratedThresholdSeconds": 3.0,
                        "frustratingThresholdSeconds": 12.0,
                    },
                    "fallbackThresholds": {
                        "toleratedFallbackThresholdSeconds": 3.0,
                        "frustratingFallbackThresholdSeconds": 12.0,
                    },
                },
            },
            {
                "schemaId": "builtin:rum.web.key-performance-metric-xhr-actions",
                "schemaVersion": "1.1.0",
                "origin": "environment",
                "value": {
                    "kpm": "RESPONSE_END",
                    "thresholds": {
                        "toleratedThresholdSeconds": 2.0,
                        "frustratingThresholdSeconds": 8.0,
                    },
                    "fallbackThresholds": {
                        "toleratedFallbackThresholdSeconds": 3.0,
                        "frustratingFallbackThresholdSeconds": 12.0,
                    },
                },
            },
            {
                "schemaId": "builtin:rum.web.key-performance-metric-custom-actions",
                "schemaVersion": "1.1.0",
                "value": {
                    "thresholds": {
                        "toleratedThresholdSeconds": 4.0,
                        "frustratingThresholdSeconds": 16.0,
                    },
                },
            },
        ],
        "nextPageKey": None,
        "totalCount": 3,
    }


def test_effective_values_export_offline_advisory_no_fabricated_action_counts():
    from rasai.dynatrace_effective_values_adapter_355 import (
        extract_apdex_from_effective_values,
    )
    supplied = _effective_values_export()
    original = json.dumps(supplied, sort_keys=True)
    parsed = extract_apdex_from_effective_values(
        supplied, declared_application_scope="APPLICATION-ABC123",
    )
    assert parsed["dynatrace_provider_requests"] == 0
    assert parsed["rasai_audit_writes"] == 0
    assert parsed["settings_provenance"].endswith("NOT_TENANT_VERIFIED")
    assert parsed["capture_flags_available"] is False
    assert parsed["action_counts_available"] is False
    assert "capture" not in parsed["settings"]
    assert parsed["settings"]["xhr_actions"]["kpm"] == "RESPONSE_END"
    assert "kpm" not in parsed["settings"]["custom_actions"]
    outcome = _assess(settings=parsed["settings"])
    assert outcome["status"] == "INSUFFICIENT_ACTION_SCOPE"
    assert "XHR_ACTION_POPULATION_NOT_PROVEN" in outcome["reasons"]
    assert outcome["recommended_numeric_thresholds"] is None
    assert json.dumps(supplied, sort_keys=True) == original


@pytest.mark.parametrize("variant", [
    "next_page", "duplicate", "foreign_schema", "count_mismatch",
    "not_a_list", "empty_value", "invalid_scope",
])
def test_effective_values_export_malformed_data_abstains(variant):
    from rasai.dynatrace_effective_values_adapter_355 import (
        extract_apdex_from_effective_values,
    )
    value = _effective_values_export()
    scope = "APPLICATION-ABC123"
    if variant == "next_page":
        value["nextPageKey"] = "opaque"
    elif variant == "duplicate":
        value["items"].append(dict(value["items"][0]))
        value["totalCount"] += 1
    elif variant == "foreign_schema":
        value["items"][0]["schemaId"] = "builtin:synthetic.browser.scheduling"
    elif variant == "count_mismatch":
        value["totalCount"] += 1
    elif variant == "not_a_list":
        value["items"] = {}
    elif variant == "empty_value":
        value["items"][0]["value"] = {}
    elif variant == "invalid_scope":
        scope = "environment"
    with pytest.raises(ValueError):
        extract_apdex_from_effective_values(value, declared_application_scope=scope)


def test_offline_effective_values_cli_is_read_only_with_explicit_unverified_scope(
    tmp_path, capsys, monkeypatch,
):
    from rasai.dynatrace_apdex_review_cli_355 import main
    path = tmp_path / "effective.json"
    path.write_text(json.dumps(_effective_values_export()), encoding="utf-8")
    import socket
    monkeypatch.setattr(socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("network must not be used")))
    digest = path.read_bytes()
    assert main([
        "--architecture", "CSR_SPA",
        "--architecture-evidence-id", "SNP-EXPORTED-UNVERIFIED",
        "--soft-navigation", "observed",
        "--async-requests", "observed",
        "--effective-values-json", str(path),
        "--application-scope", "APPLICATION-ABC123",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["input_source"] == "OPERATOR_SUPPLIED_DYNATRACE_EFFECTIVE_VALUES_EXPORT"
    assert output["actual_dynatrace_tenant_consulted"] is False
    assert output["effective_values_export"]["scope_provenance"].endswith(
        "NOT_VERIFIED_FROM_FILE"
    )
    assert output["dynatrace_provider_requests"] == 0
    assert output["synthetic_m23_m25_changed"] is False
    assert path.read_bytes() == digest
    with pytest.raises(SystemExit):
        main([
            "--architecture", "CSR_SPA",
            "--effective-values-json", str(path),
        ])

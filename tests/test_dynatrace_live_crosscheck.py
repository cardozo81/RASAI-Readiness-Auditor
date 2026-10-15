"""#355 same-live-tenant dual API coverage with two distinct read grants."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from rasai.dynatrace_live_crosscheck_355 import (
    inspect_live_dynatrace_apdex_coverage, main,
)

_APP = "APPLICATION-0123456789ABCDEF"
_URL = "https://example.org/vida"
_START = 1791626400000
_END = _START + 60 * 60 * 1000


def _settings():
    thresholds = {
        "toleratedThresholdSeconds": 2.0,
        "frustratingThresholdSeconds": 8.0,
    }
    fallback = {
        "toleratedFallbackThresholdSeconds": 3.0,
        "frustratingFallbackThresholdSeconds": 12.0,
    }
    return {
        "settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
        "actual_dynatrace_tenant_consulted": True,
        "scope_provenance": "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS",
        "declared_application_scope": _APP,
        "dynatrace_provider_requests": 1,
        "settings": {
            "load_actions": {
                "kpm": "VISUALLY_COMPLETE",
                "thresholds": thresholds, "fallbackThresholds": fallback,
            },
            "xhr_actions": {
                "kpm": "USER_ACTION_DURATION",
                "thresholds": thresholds, "fallbackThresholds": fallback,
            },
        },
    }


def _rum(*, extrapolation=4, xhr=0):
    return {
        "contract_version": "RASAI-DYNATRACE-RUM-USQL-ACTIONS-001",
        "source": "LIVE_RUM_CLASSIC_USQL_AGGREGATE_RESPONSE",
        "application_id": _APP, "target_url": _URL,
        "declared_dynatrace_device_filter": "MOBILE",
        "period_start_utc": datetime.fromtimestamp(
            _START/1000, timezone.utc,
        ).isoformat(),
        "period_end_utc": datetime.fromtimestamp(
            _END/1000, timezone.utc,
        ).isoformat(),
        "action_counts": {"load": 10, "xhr": xhr, "custom": 2, "other": 0},
        "action_count_total": 12 + xhr,
        "usql_extrapolation_level": extrapolation,
        "usql_reported_counts_extrapolated": (
            None if extrapolation is None else extrapolation > 1
        ),
        "raw_rum_action_census_verified": False,
        "rasai_same_browser_sample_verified": False,
        "population_query_scoped_to_exact_url_device_window": True,
        "rum_action_aggregate_returned": True,
        "provider_requests": 1, "audit_writes": 0,
    }


def _arguments(**overrides):
    result = {
        "base_url": "https://abc123.live.dynatrace.com",
        "application_id": _APP, "target_url": _URL,
        "dynatrace_device": "MOBILE",
        "start_timestamp_ms": _START, "end_timestamp_ms": _END,
        "architecture": "CSR_SPA",
        "architecture_evidence_id": "OPERATOR-M6-DECLARATION",
        "soft_navigation_observed": True,
        "async_requests_observed": True,
        "settings_api_token": "SETTINGS-SCOPE-SECRET",
        "usql_api_token": "USQL-SCOPE-SECRET",
    }
    result.update(overrides)
    return result


def _fakes(*, settings=None, rum=None):
    events = []
    def read_settings(**kwargs):
        events.append(("settings", kwargs))
        return _settings() if settings is None else settings
    def read_rum(**kwargs):
        events.append(("rum", kwargs))
        return _rum() if rum is None else rum
    return read_settings, read_rum, events


def test_same_tenant_gets_two_explicit_readonly_api_requests_and_no_secrets():
    read_settings, read_rum, calls = _fakes()
    input_ = _arguments()
    result = inspect_live_dynatrace_apdex_coverage(
        **input_, settings_reader=read_settings, rum_reader=read_rum,
    )
    assert [kind for kind, _ in calls] == ["settings", "rum"]
    assert calls[0][1]["application_scope"] == _APP
    assert calls[1][1]["application_id"] == _APP
    assert calls[0][1]["base_url"] == calls[1][1]["base_url"]
    assert calls[0][1]["api_token"] != calls[1][1]["api_token"]
    assert result["status"] == "SAME_LIVE_TENANT_APPLICATION_SCOPE_ONLY"
    assert result["provider_requests"] == 2
    assert result["actual_authenticated_dynatrace_get_requests"] == 2
    assert result["comparison"]["application_scope_verified_across_sources"] is True
    assert result["comparison"]["rasai_same_browser_sample_verified"] is False
    assert result["comparison"]["rum_observation_matches_architecture_sample"] is False
    assert result["comparison"]["rum_counts_are_raw_population_census"] is False
    assert result["comparison"]["action_counts_reported"]["xhr"] == 0
    assert "NO_REPORTED_XHR_ACTIONS_DOES_NOT_PROVE_CAPTURE_DISABLED" in result[
        "comparison"]["review_findings"]
    assert result["new_apdex_score"] is None
    assert result["recommended_numeric_thresholds"] is None
    assert result["audit_writes"] == 0
    assert result["synthetic_m23_m25_changed"] is False
    output = json.dumps(result)
    assert input_["settings_api_token"] not in output
    assert input_["usql_api_token"] not in output
    assert input_["base_url"] not in output


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"base_url": "https://abc.live.dynatrace.com.evil.test"}, "tenant"),
        ({"application_id": "APPLICATION-OTHER"}, "application"),
        ({"target_url": "https://example.org/vida\'bad"}, "target"),
        ({"dynatrace_device": "X\'OR"}, "device"),
        ({"start_timestamp_ms": _END}, "time"),
        ({"end_timestamp_ms": _START}, "time"),
        ({"settings_api_token": ""}, "tokens"),
        ({"usql_api_token": "LINE" + chr(10) + "INJECTION"}, "tokens"),
        ({"usql_api_token": "SETTINGS-SCOPE-SECRET"}, "distinct"),
        ({"architecture": "NOT_AN_ARCHITECTURE"}, "architecture"),
        ({"architecture_evidence_id": ""}, "architecture"),
    ],
)
def test_preflight_rejects_both_network_requests_for_invalid_argument(
    changes, reason,
):
    read_settings, read_rum, calls = _fakes()
    with pytest.raises(ValueError, match=reason):
        inspect_live_dynatrace_apdex_coverage(
            **_arguments(**changes),
            settings_reader=read_settings, rum_reader=read_rum,
        )
    assert calls == []


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"target_url": "https://wrong.example.org"}, "bounded scope"),
        ({"declared_dynatrace_device_filter": "DESKTOP"}, "bounded scope"),
        ({"period_start_utc": "2024-01-01T00:00:00+00:00"}, "bounded scope"),
        ({"application_id": "APPLICATION-FFFFFFFFFFFFFFFF"}, "bounded scope"),
        ({"population_query_scoped_to_exact_url_device_window": False}, "bounded scope"),
        ({"action_count_total": 99}, "not comparable"),
        ({"usql_reported_counts_extrapolated": False}, "not comparable"),
    ],
)
def test_cross_api_result_fails_closed_when_scope_or_counts_disagree(change, reason):
    result = _rum()
    result.update(change)
    read_settings, read_rum, calls = _fakes(rum=result)
    with pytest.raises(ValueError, match=reason):
        inspect_live_dynatrace_apdex_coverage(
            **_arguments(), settings_reader=read_settings, rum_reader=read_rum,
        )
    assert [x[0] for x in calls] == ["settings", "rum"]


def test_settings_failure_prevents_secondary_usql_request_and_error_leaks():
    calls = []
    def fail_settings(**kwargs):
        calls.append("settings")
        raise ValueError("TOP-SECRET-HTTP-RESPONSE")
    def fail_if_called(**kwargs):
        calls.append("rum")
        pytest.fail("unexpected USQL network call")
    with pytest.raises(ValueError, match="evidence unavailable") as err:
        inspect_live_dynatrace_apdex_coverage(
            **_arguments(),
            settings_reader=fail_settings, rum_reader=fail_if_called,
        )
    assert calls == ["settings"]
    assert "TOP-SECRET" not in str(err.value)


def test_cli_requires_both_explicit_flags_before_any_network(tmp_path, capsys):
    args = [
        "--live-base-url", "https://abc123.live.dynatrace.com",
        "--application-id", _APP, "--target-url", _URL,
        "--dynatrace-device", "MOBILE",
        "--start-timestamp-ms", str(_START),
        "--end-timestamp-ms", str(_END),
        "--architecture", "CSR_SPA",
        "--architecture-evidence-id", "M6-EVIDENCE-UNVERIFIED",
    ]
    for tail in ([], ["--allow-live-settings-read"], ["--allow-live-usql-read"]):
        with pytest.raises(SystemExit) as exc:
            main(args + tail)
        assert exc.value.code == 2
        assert "both explicit" in capsys.readouterr().err


def test_identical_tokens_refused_without_first_or_second_network_request():
    read_settings, read_rum, events = _fakes()
    args = _arguments(
        settings_api_token="ONE-SHARED-BROAD-TOKEN",
        usql_api_token="ONE-SHARED-BROAD-TOKEN",
    )
    with pytest.raises(ValueError, match="distinct read-only Dynatrace tokens"):
        inspect_live_dynatrace_apdex_coverage(
            **args, settings_reader=read_settings, rum_reader=read_rum,
        )
    assert events == []

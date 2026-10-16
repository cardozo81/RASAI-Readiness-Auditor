"""#355: Dynatrace RUM configuration is not RASAi's homologated synthetic Apdex."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from rasai.dynatrace_apdex_arch_advisory import (
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
    from rasai import dynatrace_apdex_arch_advisory as module
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
    from rasai.dynatrace_apdex_review_cli import main
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


@pytest.mark.parametrize("file_mode", ["settings", "effective_values"])
@pytest.mark.parametrize("defect", ["root_duplicate", "nested_duplicate", "non_json_number"])
def test_offline_review_rejects_ambiguous_local_settings_json(
    tmp_path, capsys, file_mode, defect,
):
    """#355: no last-key-wins or Python NaN extensions in local user exports."""
    from rasai.dynatrace_apdex_review_cli import main

    payload = (
        _config(xhr=True)
        if file_mode == "settings" else _effective_values_export()
    )
    raw = json.dumps(payload)
    if defect == "root_duplicate":
        raw = ('{"load_actions":null,' + raw[1:] if file_mode == "settings"
               else '{"items":[],' + raw[1:])
    elif defect == "nested_duplicate":
        assert '"kpm":' in raw
        raw = raw.replace('"kpm":', '"kpm":"INVALID", "kpm":', 1)
    else:
        raw = raw[:-1] + ',"extra":NaN}'
    assert isinstance(json.loads(raw), dict)
    source = tmp_path / "settings-export.json"
    source.write_text(raw, encoding="utf-8")
    original = source.read_bytes()
    arguments = [
        "--architecture", "CSR_SPA",
        "--architecture-evidence-id", "M6-LOCAL-ONLY",
    ]
    if file_mode == "settings":
        arguments += ["--settings-json", str(source)]
    else:
        arguments += [
            "--effective-values-json", str(source),
            "--application-scope", "APPLICATION-ABC123",
        ]
    with pytest.raises(SystemExit) as failure:
        main(arguments)
    assert failure.value.code == 2
    assert "settings JSON cannot be read or parsed" in capsys.readouterr().err
    assert source.read_bytes() == original


@pytest.mark.parametrize("defect", ["short_stream", "extra_stream"])
def test_offline_review_rejects_incomplete_physical_settings_read(
    tmp_path, monkeypatch, defect,
):
    from io import BytesIO
    from pathlib import Path
    from rasai.dynatrace_apdex_review_cli import _load_offline_snapshot

    path = tmp_path / "settings-export.json"
    original = json.dumps(_config()).encode("utf-8")
    path.write_bytes(original)
    injected = (
        original[:-7] if defect == "short_stream" else original + b"  "
    )
    normal_open = Path.open
    opened = []

    def simulated_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb":
            opened.append(1)
            return BytesIO(injected)
        return normal_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", simulated_open)
    with pytest.raises(ValueError, match="settings JSON changed during physical read"):
        _load_offline_snapshot(path)
    assert opened == [1]
    with normal_open(path, "rb") as file:
        assert file.read() == original


def test_effective_values_export_offline_advisory_no_fabricated_action_counts():
    from rasai.dynatrace_effective_values_adapter import (
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
    from rasai.dynatrace_effective_values_adapter import (
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
    from rasai.dynatrace_apdex_review_cli import main
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


@pytest.mark.parametrize(
    ("architecture", "soft", "async_seen", "expected_types"),
    [
        ("CSR_SPA", True, True, ["load_actions", "xhr_actions"]),
        ("HYDRATED", True, True, ["load_actions", "xhr_actions"]),
        ("MIXED", True, False, ["load_actions", "xhr_actions"]),
        ("STATIC_OR_SSR", False, False, ["load_actions"]),
        ("CSR_SPA", None, None, ["load_actions"]),
    ],
)
def test_pt_br_kpm_profiles_are_architecture_contextual_not_applied_defaults(
    architecture, soft, async_seen, expected_types,
):
    from rasai.dynatrace_apdex_arch_advisory import (
        explain_dynatrace_apdex_pt_br,
        KPM_BY_ACTION,
    )
    declared = _config(xhr=True, count=3) if async_seen else _config()
    advisory = assess(
        architecture=architecture,
        architecture_evidence_id="M6-DECLARED-OFFLINE",
        soft_navigation_observed=soft,
        async_requests_observed=async_seen,
        settings=declared,
    )
    projected = explain_dynatrace_apdex_pt_br(advisory)
    review = projected["revisao_de_perfis_por_arquitetura"]
    assert review["status"] == "CONTEXTUAL_KPM_OPTIONS_NOT_VERIFIED_RECOMMENDATION"
    assert [p["action_type"] for p in review["profiles"]] == expected_types
    assert review["settings_auto_applied"] is False
    assert review["numeric_thresholds"] is None
    for profile in review["profiles"]:
        assert profile["vendor_valid_kpm_options"] == sorted(
            KPM_BY_ACTION[profile["action_type"]]
        )
        assert profile["prescribed_kpm"] is None
        assert profile["prescribed_tolerated_seconds"] is None
        assert profile["prescribed_frustrating_seconds"] is None
    assert advisory["dynatrace_provider_requests"] == 0
    assert advisory["synthetic_m23_m25_changed"] is False
    assert advisory["new_apdex_score"] is None


def test_pt_br_kpm_profiles_do_not_label_absent_xhr_as_disabled_capture():
    from rasai.dynatrace_apdex_arch_advisory import (
        explain_dynatrace_apdex_pt_br,
    )
    advisory = _assess(settings=_config(), architecture="CSR_SPA")
    out = explain_dynatrace_apdex_pt_br(advisory)
    xhr = next(
        item for item in out["revisao_de_perfis_por_arquitetura"]["profiles"]
        if item["action_type"] == "xhr_actions"
    )
    assert xhr["configuration_presence"] == (
        "KPM_NOT_PROVIDED_NOT_PROOF_OF_DISABLED_CAPTURE"
    )
    assert xhr["configured_kpm"] is None
    assert xhr["review"] == "REVIEW_RUM_XHR_CAPTURE_AND_ACTION_COVERAGE"


def test_pt_br_kpm_profile_custom_action_and_unknown_architecture_abstain():
    from rasai.dynatrace_apdex_arch_advisory import (
        explain_dynatrace_apdex_pt_br,
    )
    settings = _config(xhr=True, count=5)
    settings["custom_actions"] = {
        "kpm": "USER_ACTION_DURATION",
        "thresholds": _thresholds(),
    }
    known = explain_dynatrace_apdex_pt_br(
        _assess(settings=settings, architecture="HYDRATED")
    )
    custom = known["revisao_de_perfis_por_arquitetura"]["profiles"][-1]
    assert custom["action_type"] == "custom_actions"
    assert custom["vendor_valid_kpm_options"] == ["USER_ACTION_DURATION"]
    assert custom["configured_kpm"] == "USER_ACTION_DURATION"
    unknown = explain_dynatrace_apdex_pt_br(
        _assess(settings=settings, architecture="UNKNOWN")
    )
    guidance = unknown["revisao_de_perfis_por_arquitetura"]
    assert guidance["status"] == "ARCHITECTURE_NOT_VERIFIED"
    assert guidance["profiles"] == []
    assert guidance["settings_auto_applied"] is False
    assert guidance["numeric_thresholds"] is None


def test_pt_br_advisory_spa_load_only_never_claims_captured_xhr():
    from rasai.dynatrace_apdex_arch_advisory import explain_dynatrace_apdex_pt_br
    verdict = _assess(settings=_config())
    explanation = explain_dynatrace_apdex_pt_br(verdict)
    assert explanation["conclusao"] == "Cobertura das ações não comprovada"
    assert explanation["metricas_declaradas_na_configuracao"] == {"Load": "VISUALLY_COMPLETE"}
    assert "Configuração de Apdex XHR não fornecida" in explanation["motivos"]
    assert "não comprova captura" in explanation["limite_metodologico"]
    assert "mesma amostra" in explanation["limite_metodologico"]
    assert explanation["arquitetura_informada"] == "CSR_SPA"


def test_pt_br_advisory_rejects_fabricated_metrics_and_surfaces_threshold_reasons():
    from rasai.dynatrace_apdex_arch_advisory import explain_dynatrace_apdex_pt_br
    cfg = _config(xhr=True)
    cfg["xhr_actions"]["kpm"] = "SPEED_INDEX"
    invalid = _assess(settings=cfg)
    report = explain_dynatrace_apdex_pt_br(invalid)
    assert report["metricas_declaradas_na_configuracao"] == {}
    assert "XHR: KPM incompatível com o tipo de ação" in report["motivos"]
    assert report["conclusao"] == "Configuração fornecida inconsistente ou inválida"


def test_pt_br_offline_cli_explains_unknown_without_ever_claiming_real_rum(
    tmp_path, capsys,
):
    from rasai.dynatrace_apdex_review_cli import main
    assert main(["--architecture", "UNKNOWN"]) == 0
    payload = json.loads(capsys.readouterr().out)
    message = payload["analyst_guidance_pt_br"]
    assert message["conclusao"] == "Diagnóstico não determinável com as evidências fornecidas"
    assert message["motivos"] == ["Arquitetura não determinada"]
    assert message["metricas_declaradas_na_configuracao"] == {}
    assert payload["actual_dynatrace_tenant_consulted"] is False
    assert payload["audit_writes"] == payload["dynatrace_provider_requests"] == 0


def test_settings_read_live_adapter_uses_exact_scoped_get_and_not_redirects():
    from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings
    class Reply:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def getcode(self):
            return 200
        def read(self, max_bytes):
            assert max_bytes == 1024 * 1024 + 1
            return json.dumps(_effective_values_export()).encode("utf-8")
    class FakeOpener:
        def __init__(self):
            self.calls = []
        def open(self, request, timeout):
            self.calls.append((request, timeout))
            return Reply()
    fake = FakeOpener()
    result = read_live_dynatrace_apdex_settings(
        base_url="https://abc123.live.dynatrace.com",
        application_scope="APPLICATION-ABC123",
        api_token="SECRET-TOKEN-NOT-LOGGED",
        opener=fake,
    )
    assert len(fake.calls) == 1
    request, timeout = fake.calls[0]
    assert request.get_method() == "GET"
    assert request.full_url.startswith(
        "https://abc123.live.dynatrace.com/api/v2/settings/effectiveValues?"
    )
    assert "scope=APPLICATION-ABC123" in request.full_url
    assert "schemaIds=" in request.full_url
    assert "Api-Token SECRET" in request.get_header("Authorization")
    assert timeout == 10.0
    assert result["actual_dynatrace_tenant_consulted"] is True
    assert result["settings_provenance"] == "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
    assert result["rum_action_population_verified"] is False
    assert result["rasai_same_page_device_time_verified"] is False
    assert result["dynatrace_provider_requests"] == 1
    assert "SECRET-TOKEN" not in json.dumps(result)


@pytest.mark.parametrize("url", [
    "http://abc.live.dynatrace.com",
    "https://abc.live.dynatrace.com.evil.org",
    "https://abc.live.dynatrace.com/path",
    "https://user@abc.live.dynatrace.com",
    "https://abc.live.dynatrace.com:443",
    "https://abc.live.dynatrace.com/?token=abc",
    " https://abc.live.dynatrace.com",
    "https://localhost",
    "https://127.0.0.1",
])
def test_settings_read_rejects_unsafe_environment_before_network(url):
    from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings
    class NoNetwork:
        def open(self, *_args, **_kwargs):
            pytest.fail("invalid request reached transport")
    with pytest.raises(ValueError):
        read_live_dynatrace_apdex_settings(
            base_url=url, application_scope="APPLICATION-ABC123",
            api_token="PRIVATE", opener=NoNetwork(),
        )


def test_settings_read_missing_token_bad_scope_and_pagination_no_false_success():
    from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings
    class Never:
        def open(self, *_args, **_kwargs):
            pytest.fail("unexpected outbound call")
    for token, scope in (("", "APPLICATION-ABC123"),
                         ("SECRET" + chr(10) + "LEAK", "APPLICATION-ABC123"),
                         ("valid", "environment")):
        with pytest.raises(ValueError):
            read_live_dynatrace_apdex_settings(
                base_url="https://abc.live.dynatrace.com",
                application_scope=scope, api_token=token, opener=Never(),
            )

    class Paged:
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def getcode(self):
            return 200
        def read(self, _):
            return json.dumps(self.payload).encode("utf-8")
    class Open:
        def open(self, request, timeout):
            paged = _effective_values_export()
            paged["nextPageKey"] = "another-page"
            return Paged(paged)
    with pytest.raises(ValueError, match="paginated"):
        read_live_dynatrace_apdex_settings(
            base_url="https://abc.live.dynatrace.com",
            application_scope="APPLICATION-ABC123",
            api_token="SECRET", opener=Open(),
        )


def test_cli_live_settings_requires_opt_in_and_keeps_no_secrets(tmp_path, monkeypatch, capsys):
    from rasai.dynatrace_apdex_review_cli import main
    from rasai import dynatrace_apdex_review_cli as cli
    monkeypatch.setenv("DYNATRACE_API_TOKEN", "SENSITIVE_NEVER_RENDER")
    calls = []
    def fake_read(**kwargs):
        calls.append(kwargs)
        result = {
            "settings": _config(xhr=True, count=4),
            "settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
            "scope_provenance": "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS",
        }
        return result
    monkeypatch.setattr(cli, "read_live_dynatrace_apdex_settings", fake_read)
    args = ["--architecture", "CSR_SPA",
            "--architecture-evidence-id", "SNP-1",
            "--soft-navigation", "observed",
            "--async-requests", "observed",
            "--application-scope", "APPLICATION-ABC123",
            "--live-base-url", "https://abc.live.dynatrace.com"]
    with pytest.raises(SystemExit):
        main(args)
    assert calls == []
    capsys.readouterr()
    assert main(args + ["--allow-live-settings-read"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(calls) == 1 and calls[0]["api_token"] == "SENSITIVE_NEVER_RENDER"
    assert payload["settings_provenance"] == "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
    assert payload["actual_dynatrace_tenant_consulted"] is True
    assert payload["dynatrace_provider_requests"] == 1
    assert payload["rasai_same_page_device_time_verified"] is False
    assert "Valores efetivos consultados" in payload["analyst_guidance_pt_br"]["limite_metodologico"]
    assert "SENSITIVE_NEVER_RENDER" not in json.dumps(payload)


@pytest.mark.parametrize("incomplete", [
    {"settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"},
    {"settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
     "actual_dynatrace_tenant_consulted": True},
    {"settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
     "actual_dynatrace_tenant_consulted": True, "dynatrace_provider_requests": 1},
    {"settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
     "actual_dynatrace_tenant_consulted": True, "dynatrace_provider_requests": 1,
     "input_source": "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"},
    {"settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
     "actual_dynatrace_tenant_consulted": True, "dynatrace_provider_requests": True,
     "input_source": "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES",
     "scope_provenance": "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS"},
])
def test_355_operator_provenance_string_does_not_certify_live_tenant_read(incomplete):
    from rasai.dynatrace_apdex_arch_advisory import explain_dynatrace_apdex_pt_br

    answer = _assess()
    answer.update(incomplete)
    before = deepcopy(answer)
    description = explain_dynatrace_apdex_pt_br(answer)
    assert "não verificada no tenant" in description["limite_metodologico"]
    assert "Valores efetivos consultados" not in description["limite_metodologico"]
    assert answer == before
    assert answer["dynatrace_provider_requests"] in (0, 1, True)


def test_355_live_message_requires_all_cli_transport_scope_contract_fields():
    from rasai.dynatrace_apdex_arch_advisory import explain_dynatrace_apdex_pt_br

    answer = _assess()
    answer.update({
        "input_source": "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES",
        "scope_provenance": "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS",
        "settings_provenance": "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES",
        "actual_dynatrace_tenant_consulted": True,
        "dynatrace_provider_requests": 1,
    })
    rendering = explain_dynatrace_apdex_pt_br(answer)
    assert "Valores efetivos consultados" in rendering["limite_metodologico"]
    assert "não comprova captura" in rendering["limite_metodologico"]
    assert "mesma amostra" in rendering["limite_metodologico"]


def test_355_same_size_atomic_snapshot_swap_between_stat_and_open_is_rejected(
    tmp_path, monkeypatch,
):
    """Bytes matching old size do not prove the opened file is the inspected one."""
    import os
    from pathlib import Path
    from rasai.dynatrace_apdex_review_cli import _load_offline_snapshot

    path = tmp_path / "dynatrace.json"
    before = json.dumps(_config(xhr=False), sort_keys=True).encode("utf-8")
    path.write_bytes(before)
    alternate = tmp_path / "alternate.json"
    replacement = before.replace(b"VISUALLY_COMPLETE", b"USER_ACTION_DURAT")
    assert replacement != before and len(replacement) == len(before)
    alternate.write_bytes(replacement)
    normal_open = Path.open
    replaced = []

    def swap_file_before_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb" and not replaced:
            os.replace(alternate, path)
            replaced.append(True)
        return normal_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swap_file_before_open)
    with pytest.raises(ValueError, match="settings JSON changed during physical read"):
        _load_offline_snapshot(path)
    assert replaced == [True]
    with normal_open(path, "rb") as source:
        assert source.read() == replacement


def test_355_same_length_in_place_rewrite_during_snapshot_open_is_rejected(
    tmp_path, monkeypatch,
):
    """The source may be edited in place without changing its byte count."""
    import os
    from pathlib import Path
    from rasai.dynatrace_apdex_review_cli import _load_offline_snapshot

    path = tmp_path / "dynatrace-in-place.json"
    original = json.dumps(_config(xhr=True), sort_keys=True).encode("utf-8")
    replacement = original.replace(b"VISUALLY_COMPLETE", b"USER_ACTION_DURAT")
    assert replacement != original and len(replacement) == len(original)
    path.write_bytes(original)
    initial = path.stat()
    normal_open = Path.open
    modified = []

    def update_before_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb" and not modified:
            # Rewrite file in place, preserving size. Set mtime explicitly to
            # a different value so the source-drift assertion is deterministic
            # even on coarse timestamp file systems.
            path.write_bytes(replacement)
            os.utime(path, ns=(initial.st_atime_ns, initial.st_mtime_ns + 2_000_000_000))
            modified.append(True)
        return normal_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", update_before_open)
    with pytest.raises(ValueError, match="settings JSON changed during physical read"):
        _load_offline_snapshot(path)
    assert modified == [True]
    with normal_open(path, "rb") as source:
        assert source.read() == replacement


def test_missing_custom_action_kpm_cannot_be_reported_as_observed():
    settings = _config(xhr=True, count=12, capture={"xhr": True, "fetch": True})
    settings["custom_actions"] = {"thresholds": _thresholds()}
    result = _assess(settings=settings)
    assert result["status"] == "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE"
    assert "custom_actions" not in result["observed_kpm"]
    assert result["observed_kpm"]["xhr_actions"] == "USER_ACTION_DURATION"
    assert result["recommended_numeric_thresholds"] is None

    # Explicit KPM retains the documented custom-actions rule.
    settings["custom_actions"]["kpm"] = "USER_ACTION_DURATION"
    supported = _assess(settings=settings)
    assert supported["status"] == "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE"
    assert supported["observed_kpm"]["custom_actions"] == "USER_ACTION_DURATION"


@pytest.mark.parametrize("which", ["toleratedThresholdSeconds", "frustratingThresholdSeconds"])
def test_oversized_json_integer_threshold_abstains_without_overflow(which):
    conf = _config()
    conf["load_actions"]["thresholds"][which] = 10 ** 400
    out = _assess(settings=conf)
    assert out["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert "load_actions:INVALID_APDEX_THRESHOLDS" in out["reasons"]
    assert out["observed_kpm"] == {}
    assert out["new_apdex_score"] is None


@pytest.mark.parametrize("invalid", [[], {}, {"class": "CSR_SPA"}, 123])
def test_malformed_architecture_input_abstains(invalid):
    result = _assess(architecture=invalid)
    assert result["status"] == "NOT_EVALUABLE"
    assert result["reasons"] == ["ARCHITECTURE_NOT_PROVEN"]
    assert result["new_apdex_score"] is None


def test_dynatrace_action_counts_cannot_be_unbounded_claims() -> None:
    config = _config(xhr=True, count=100_000_001)
    result = _assess(settings=config)
    assert result["status"] == "INVALID_SETTINGS_SNAPSHOT"
    assert "action_counts:INVALID_POPULATION" in result["reasons"]
    assert result["new_apdex_score"] is None


@pytest.mark.parametrize("bad_timeout", [True, 0, -1, float("nan"), float("inf"), "10"])
def test_live_settings_timeout_rejected_before_provider_request(bad_timeout):
    from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings
    with pytest.raises(ValueError, match="timeout"):
        read_live_dynatrace_apdex_settings(
            base_url="https://tenant.live.dynatrace.com",
            application_scope="APPLICATION-1234567890ABCDEF",
            api_token="fake-offline-test-token", timeout_seconds=bad_timeout,
        )


def test_live_settings_token_control_character_rejected_before_provider_request():
    from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings
    with pytest.raises(ValueError, match="token"):
        read_live_dynatrace_apdex_settings(
            base_url="https://tenant.live.dynatrace.com",
            application_scope="APPLICATION-1234567890ABCDEF",
            api_token="not-a-valid\ttoken", timeout_seconds=10,
        )

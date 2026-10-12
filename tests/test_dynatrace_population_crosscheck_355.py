"""#355: no-provider Dynatrace settings vs USQL scope and sampling cross-check."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from rasai.dynatrace_population_crosscheck_355 import (
    compare_dynatrace_settings_and_rum as compare,
    main,
)


_APP = "APPLICATION-1234567890ABCDEF"


def _settings(*, live=True, xhr=True, arch="CSR_SPA"):
    return {
        "contract_version": "RASAI-DYNATRACE-APDEX-ARCHITECTURE-ADVISORY-001",
        "input_source": (
            "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"
            if live else "OPERATOR_SUPPLIED_DYNATRACE_EFFECTIVE_VALUES_EXPORT"
        ),
        "settings_provenance": (
            "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
            if live else "OPERATOR_SUPPLIED_API_EXPORT_NOT_TENANT_VERIFIED"
        ),
        "actual_dynatrace_tenant_consulted": live,
        "effective_values_export": {"declared_application_scope": _APP},
        "architecture": arch,
        "status": "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE",
        "observed_kpm": (
            {"load_actions": "VISUALLY_COMPLETE",
             "xhr_actions": "USER_ACTION_DURATION"}
            if xhr else {"load_actions": "VISUALLY_COMPLETE"}
        ),
        "new_apdex_score": None,
        "synthetic_m23_m25_changed": False,
    }


def _rum(*, xhr=0, extrap=4):
    return {
        "contract_version": "RASAI-DYNATRACE-RUM-USQL-ACTIONS-001",
        "source": "LIVE_RUM_CLASSIC_USQL_AGGREGATE_RESPONSE",
        "application_id": _APP,
        "target_url": "https://www.example.com/seguro",
        "declared_dynatrace_device_filter": "MOBILE",
        "period_start_utc": "2026-10-10T10:00:00+00:00",
        "period_end_utc": "2026-10-10T11:00:00+00:00",
        "action_counts": {"load": 10, "xhr": xhr, "custom": 2, "other": 0},
        "action_count_total": 12 + xhr,
        "usql_extrapolation_level": extrap,
        "usql_reported_counts_extrapolated": (
            None if extrap is None else extrap > 1
        ),
        "raw_rum_action_census_verified": False,
        "rasai_same_browser_sample_verified": False,
        "population_query_scoped_to_exact_url_device_window": True,
        "rum_action_aggregate_returned": True,
        "audit_writes": 0,
        "provider_requests": 1,
    }


def test_extrapolated_zero_xhr_provokes_review_not_disabled_capture_claim():
    original_settings = _settings()
    original_rum = _rum(xhr=0)
    before = json.dumps((original_settings, original_rum), sort_keys=True)
    out = compare(original_settings, original_rum)
    assert out["status"] == "CLAIMED_LIVE_APPLICATION_ID_MATCH"
    assert out["settings_export_claims_live_origin"] is True
    assert out["application_scope_verified_across_sources"] is False
    assert out["rum_counts_are_raw_population_census"] is False
    assert out["action_counts_reported"]["xhr"] == 0
    assert out["usql_extrapolation_level"] == 4
    assert "NO_REPORTED_XHR_ACTIONS_DOES_NOT_PROVE_CAPTURE_DISABLED" in out[
        "review_findings"
    ]
    assert "RUM_COUNTS_EXTRAPOLATED_NOT_RAW_CENSUS" in out["review_findings"]
    assert "INITIAL_LOAD_COUNTS_DO_NOT_PROVE_SOFT_ROUTE_READINESS" in out[
        "review_findings"
    ]
    assert out["rasai_same_browser_sample_verified"] is False
    assert out["new_apdex_score"] is None
    assert out["synthetic_m23_m25_changed"] is False
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert json.dumps((original_settings, original_rum), sort_keys=True) == before


def test_rum_xhr_population_without_configured_xhr_kpm_not_a_score():
    out = compare(_settings(xhr=False), _rum(xhr=18, extrap=1))
    assert "XHR_ACTIONS_REPORTED_WITHOUT_MATCHING_KPM_SNAPSHOT" in out[
        "review_findings"
    ]
    assert out["action_apdex_kpm"] == {"load_actions": "VISUALLY_COMPLETE"}
    assert out["new_apdex_score"] is None
    assert out["application_scope_verified_across_sources"] is False


def test_offline_user_export_only_matches_declared_scope_without_auth():
    out = compare(_settings(live=False), _rum(xhr=8, extrap=None))
    assert out["status"] == "DECLARED_APPLICATION_ID_MATCH"
    assert out["settings_export_claims_live_origin"] is False
    assert "SETTINGS_SCOPE_IS_OPERATOR_DECLARED_NOT_AUTHENTICATED" in out[
        "review_findings"
    ]
    assert "RUM_EXTRAPOLATION_LEVEL_UNKNOWN" in out["review_findings"]
    assert out["application_scope_verified_across_sources"] is False


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda s, r: r.update(application_id="APPLICATION-OTHER"),
         "APPLICATION_SCOPE_NOT_MATCHED"),
        (lambda s, r: r.update(action_count_total=900),
         "RUM_ACTION_COUNTS_INVALID"),
        (lambda s, r: r["action_counts"].update(xhr=True),
         "RUM_ACTION_COUNTS_INVALID"),
        (lambda s, r: r.update(usql_reported_counts_extrapolated=False),
         "RUM_EXTRAPOLATION_PROVENANCE_INVALID"),
        (lambda s, r: r.update(raw_rum_action_census_verified=True),
         "RUM_USQL_PROVENANCE_NOT_VERIFIED"),
        (lambda s, r: s.update(status="INVALID_SETTINGS_SNAPSHOT"),
         "SETTINGS_ADVISORY_NOT_ELIGIBLE"),
        (lambda s, r: s.update(observed_kpm=[]),
         "SETTINGS_KPM_NOT_AVAILABLE"),
        (lambda s, r: r.update(contract_version="UNSUPPORTED"),
         "RUM_USQL_VERSION_UNSUPPORTED"),
    ],
    ids=["different-app", "wrong-total", "boolean-count",
         "false-extrapolation", "invented-raw-census", "settings-invalid",
         "broken-kpm", "unsupported-rum"],
)
def test_fail_closed_on_cross_system_evidence_mismatch(mutator, reason):
    settings, rum = _settings(), _rum()
    mutator(settings, rum)
    out = compare(settings, rum)
    assert out["status"] == "NOT_COMPARABLE"
    assert out["reason"] == reason
    assert out["new_apdex_score"] is None
    assert out["application_scope_verified_across_sources"] is False


def test_ssr_load_and_unknown_are_noncausal():
    ssr = compare(_settings(arch="STATIC_OR_SSR"), _rum(xhr=0))
    assert "LOAD_ACTION_COUNTS_DO_NOT_PROVE_SAME_PAGE_SAMPLE" in ssr[
        "review_findings"
    ]
    unknown = compare(_settings(arch="UNKNOWN"), _rum(xhr=5))
    assert "ARCHITECTURE_NOT_COMPARABLE_WITH_RUM_ACTION_POPULATION" in unknown[
        "review_findings"
    ]


def test_offline_cli_reads_bounded_json_without_network_or_mutation(tmp_path, capsys):
    a = tmp_path / "settings.json"
    b = tmp_path / "rum.json"
    a.write_text(json.dumps(_settings()), encoding="utf-8")
    b.write_text(json.dumps(_rum()), encoding="utf-8")
    before = a.read_bytes(), b.read_bytes()
    assert main(["--settings-advisory-json", str(a),
                 "--rum-population-json", str(b)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "CLAIMED_LIVE_APPLICATION_ID_MATCH"
    assert result["provider_requests"] == 0
    assert (a.read_bytes(), b.read_bytes()) == before
    b.write_text("not-json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--settings-advisory-json",str(a),
              "--rum-population-json",str(b)])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda x: x.pop("population_query_scoped_to_exact_url_device_window"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(population_query_scoped_to_exact_url_device_window=False),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.pop("rum_action_aggregate_returned"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(target_url="javascript:alert(1)"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(target_url="https://www.example.com/seguro/"),
         None),
        (lambda x: x.update(declared_dynatrace_device_filter=""),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(period_start_utc="2026-10-10T10:00:00"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(period_end_utc="2026-10-10T09:00:00Z"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(period_end_utc="2026-10-12T00:00:00Z"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
        (lambda x: x.update(period_start_utc="2026-10-10T07:00:00-03:00"),
         "RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE"),
    ],
    ids=[
        "missing-url-device-window-claim", "false-exact-scope-claim",
        "missing-aggregated-result", "bad-target-url", "different-safe-target-url",
        "missing-device", "naive-UTC-start", "reversed-time", "over-24h",
        "non-UTC-offset",
    ],
)
def test_v2_rum_scope_metadata_must_be_complete_and_consistent(mutator, reason):
    rum = _rum()
    settings = _settings()
    mutator(rum)
    before = json.dumps((rum, settings), sort_keys=True)
    result = compare(settings, rum)
    assert result["contract_version"] == (
        "RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002"
    )
    if reason is not None:
        assert result["status"] == "NOT_COMPARABLE"
        assert result["reason"] == reason
        assert "action_counts_reported" not in result
        assert result["application_scope_verified_across_sources"] is False
    else:
        assert result["status"] == "CLAIMED_LIVE_APPLICATION_ID_MATCH"
        # Even a different syntactically valid target URL in a forged JSON
        # cannot authenticate tenant, page or session.
        assert result["rasai_same_browser_sample_verified"] is False
        assert result["application_scope_verified_across_sources"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert result["new_apdex_score"] is None
    assert json.dumps((rum, settings), sort_keys=True) == before


def test_offline_crosscheck_html_explains_spa_xhr_and_extrapolation(
    tmp_path, capsys,
):
    from rasai.dynatrace_population_crosscheck_html_355 import (
        render_dynatrace_population_crosscheck_html,
    )
    settings = _settings()
    settings["observed_kpm"]["load_actions"] = '<img src=x onerror="alert(355)">'
    rum = _rum(xhr=0, extrap=4)
    a, b = tmp_path / "settings.json", tmp_path / "rum.json"
    a.write_text(json.dumps(settings), encoding="utf-8")
    b.write_text(json.dumps(rum), encoding="utf-8")
    before = a.read_bytes(), b.read_bytes()
    assert main([
        "--settings-advisory-json", str(a),
        "--rum-population-json", str(b),
        "--format", "html",
    ]) == 0
    html = capsys.readouterr().out
    assert "<!doctype html>" in html
    assert '<html lang="pt-BR">' in html
    assert "&lt;img src=x onerror=&quot;alert(355)&quot;&gt;" in html
    assert '<img src=x onerror="alert(355)">' not in html
    assert "SPA client-side (CSR)" in html
    assert "Load" in html and "XHR" in html and "Custom" in html
    assert "Nível 4 informado; contagens extrapoladas" in html
    assert "zero xhr não prova captura desativada" in html.lower()
    assert "Mesmo tenant, navegador" in html
    assert "@media print" in html and "@media(max-width:680px)" in html
    assert "Nenhum threshold foi inferido" in html
    assert "SCORE-GEO" in html
    assert (a.read_bytes(), b.read_bytes()) == before
    assert render_dynatrace_population_crosscheck_html(
        compare(settings, rum)
    ).startswith("<!doctype html>")


def test_dynatrace_html_rejects_false_status_and_respects_nd(tmp_path):
    from rasai.dynatrace_population_crosscheck_html_355 import (
        render_dynatrace_population_crosscheck_html as render,
    )
    out = compare(_settings(), _rum())
    out["status"] = "NOT_COMPARABLE"
    out["reason"] = '<script>alert("untrusted")</script>'
    out["action_counts_reported"] = {
        "load": 999, "xhr": 888, "custom": 777, "other": 666
    }
    out["target_url"] = "<img onerror=alert(1)>"
    html = render(out)
    assert "N/D - fontes não comparáveis" in html
    assert "&lt;script&gt;alert(&quot;untrusted&quot;)&lt;/script&gt;" in html
    assert "<script>" not in html and "<img onerror=" not in html
    assert "999" not in html and "888" not in html
    assert "<th scope='row'>XHR</th><td>N/D</td>" in html
    assert "Same" not in html
    with pytest.raises(ValueError, match="v2 projection"):
        render({"contract_version": "UNSUPPORTED", "status": "NOT_COMPARABLE"})
    projection = compare(_settings(), _rum())
    projection["review_findings"] = [{"danger": "not a code"}]
    with pytest.raises(ValueError, match="missing evidence sets"):
        render(projection)

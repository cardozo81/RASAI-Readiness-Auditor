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


@pytest.mark.parametrize("input_kind", ("settings", "rum"))
@pytest.mark.parametrize("collision", ("duplicate_root", "duplicate_nested", "non_json_number"))
def test_offline_crosscheck_cli_rejects_ambiguous_source_json(
    tmp_path, capsys, input_kind, collision,
):
    """#355: offline JSON supplied by an operator cannot authenticate itself."""
    settings_path = tmp_path / "settings.json"
    rum_path = tmp_path / "rum.json"
    original_settings = json.dumps(_settings())
    original_rum = json.dumps(_rum())
    raw = original_settings if input_kind == "settings" else original_rum
    if collision == "duplicate_root":
        duplicate = (
            '"contract_version":"FORGED",'
            + raw[1:]
        )
        raw = "{" + duplicate
    elif collision == "duplicate_nested":
        key = (
            '"declared_application_scope": '
            if input_kind == "settings" else '"xhr": '
        )
        assert key in raw
        raw = raw.replace(
            key,
            ('"declared_application_scope": "APPLICATION-OTHER", '
             if input_kind == "settings" else '"xhr": 999, ') + key,
            1,
        )
    else:
        raw = raw[:-1] + ',"unverified":NaN}'
    assert isinstance(json.loads(raw), dict)
    settings_path.write_text(
        raw if input_kind == "settings" else original_settings,
        encoding="utf-8",
    )
    rum_path.write_text(
        raw if input_kind == "rum" else original_rum,
        encoding="utf-8",
    )
    originals = (settings_path.read_bytes(), rum_path.read_bytes())
    with pytest.raises(SystemExit) as err:
        main([
            "--settings-advisory-json", str(settings_path),
            "--rum-population-json", str(rum_path),
        ])
    assert err.value.code == 2
    assert (settings_path.read_bytes(), rum_path.read_bytes()) == originals
    assert "JSON evidence unreadable or invalid" in capsys.readouterr().err


@pytest.mark.parametrize("fault", ("truncated_stream", "oversized_stream"))
def test_offline_crosscheck_rejects_stream_size_mismatch(
    tmp_path, monkeypatch, fault,
):
    """#355: the initial filesystem length, read bytes and final length agree."""
    from io import BytesIO
    from pathlib import Path
    from rasai.dynatrace_population_crosscheck_355 import _load

    file = tmp_path / "rum.json"
    physical = json.dumps(_rum()).encode("utf-8")
    file.write_bytes(physical)
    original_open = Path.open
    observed = (
        physical[:-6] if fault == "truncated_stream"
        else physical + b"      "
    )
    opens = []
    def fake_open(self, mode="r", *args, **kwargs):
        if self == file and mode == "rb":
            opens.append(1)
            return BytesIO(observed)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)
    with pytest.raises(ValueError, match="JSON evidence unreadable or invalid"):
        _load(file, 256 * 1024)
    assert opens == [1]
    with original_open(file, "rb") as handle:
        assert handle.read() == physical


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


@pytest.mark.parametrize(
    ("category", "kpm"),
    [
        ("load_actions", "NOT_OFFICIAL_KPM"),
        ("xhr_actions", "SPEED_INDEX"),
        ("custom_actions", "VISUALLY_COMPLETE"),
        ("unexpected_action_type", "USER_ACTION_DURATION"),
    ],
)
def test_offline_crosscheck_abstains_from_unsupported_action_specific_kpm(
    category, kpm,
):
    settings, rum = _settings(), _rum(xhr=5)
    settings["observed_kpm"][category] = kpm
    before = json.dumps((settings, rum), sort_keys=True)
    result = compare(settings, rum)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SETTINGS_KPM_PROJECTION_UNVERIFIABLE"
    assert "action_apdex_kpm" not in result
    assert "action_counts_reported" not in result
    assert result["new_apdex_score"] is None
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert json.dumps((settings, rum), sort_keys=True) == before


def test_offline_crosscheck_rejects_empty_kpm_snapshot_without_counts(tmp_path, capsys):
    settings = _settings()
    settings["observed_kpm"] = {}
    a, b = tmp_path / "settings.json", tmp_path / "rum.json"
    a.write_text(json.dumps(settings), encoding="utf-8")
    b.write_text(json.dumps(_rum(xhr=12)), encoding="utf-8")
    before = a.read_bytes(), b.read_bytes()
    assert main(["--settings-advisory-json", str(a),
                 "--rum-population-json", str(b), "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert "N/D - fontes não comparáveis" in html
    assert "<th scope='row'>XHR</th><td>N/D</td>" in html
    assert "Nenhuma cobertura por ação foi comprovada" in html
    assert "12</td>" not in html
    assert (a.read_bytes(), b.read_bytes()) == before


def test_offline_crosscheck_html_does_not_expose_untrusted_kpm_payload():
    from rasai.dynatrace_population_crosscheck_html_355 import (
        render_dynatrace_population_crosscheck_html,
    )
    settings = _settings()
    payload = '<img src=x onerror="alert(355)">'
    settings["observed_kpm"]["load_actions"] = payload
    result = compare(settings, _rum(xhr=8))
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SETTINGS_KPM_PROJECTION_UNVERIFIABLE"
    html = render_dynatrace_population_crosscheck_html(result)
    assert "N/D - fontes não comparáveis" in html
    assert payload not in html
    assert "alert(355)" not in html
    assert "Não concluir configuração" in html


def test_native_dynatrace_rum_crosscheck_html_and_json_bypass_audit_and_secrets(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint

    settings, rum = tmp_path / "settings.json", tmp_path / "rum.json"
    settings.write_text(json.dumps(_settings()), encoding="utf-8")
    rum.write_text(json.dumps(_rum(xhr=0, extrap=4)), encoding="utf-8")
    original = (settings.read_bytes(), rum.read_bytes())
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("offline crosscheck must not install audit runtime"),
    )
    monkeypatch.setattr(
        entrypoint, "_activate_persisted_cli_secrets",
        lambda: pytest.fail("offline crosscheck must not activate secrets"),
    )
    flags = [
        "--settings-advisory-json", str(settings),
        "--rum-population-json", str(rum),
    ]
    assert entrypoint.main(["dynatrace-rum-crosscheck", *flags, "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert html.startswith("<!doctype html>")
    assert "SPA client-side (CSR)" in html
    assert "XHR" in html
    assert "Mesmo tenant, navegador" in html
    assert "Nenhum threshold foi inferido" in html

    assert entrypoint.main(["dynatrace-rum-review", *flags, "--format", "json"]) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["contract_version"] == (
        "RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002"
    )
    assert projection["status"] == "CLAIMED_LIVE_APPLICATION_ID_MATCH"
    assert projection["application_scope_verified_across_sources"] is False
    assert projection["rasai_same_browser_sample_verified"] is False
    assert projection["recommended_numeric_thresholds"] is None
    assert projection["provider_requests"] == projection["audit_writes"] == 0
    assert (settings.read_bytes(), rum.read_bytes()) == original
    assert set(path.name for path in tmp_path.iterdir()) == {
        "settings.json", "rum.json",
    }


def test_native_dynatrace_crosscheck_missing_or_malformed_sources_fail_closed(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint

    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("offline command must not install runtime"),
    )
    first = tmp_path / "settings.json"
    second = tmp_path / "rum.json"
    first.write_text(json.dumps(_settings()), encoding="utf-8")
    original = first.read_bytes()
    args = ["dynatrace-rum-crosscheck",
            "--settings-advisory-json", str(first),
            "--rum-population-json", str(second)]
    with pytest.raises(SystemExit) as exc:
        entrypoint.main(args)
    assert exc.value.code == 2
    capsys.readouterr()
    second.write_text("{invalid", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        entrypoint.main(args)
    assert exc.value.code == 2
    assert first.read_bytes() == original

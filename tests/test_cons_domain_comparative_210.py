"""#210: pure same-domain advisory, never productive CONS or score reanalysis."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from rasai.consolidation.domain_comparative_preview_210 import preview_same_domain_candidates
from rasai.consolidation.selection import AuditCandidate


def _candidate(
    audit: str, url: str, *, device="MOBILE", status="COMPLETED",
    completion="COMPLETE", timestamp="2026-10-09T10:00:00+00:00",
) -> AuditCandidate:
    return AuditCandidate(
        audit_id=audit, event_time=timestamp, url=url,
        domain="not-a-proof", device=device,
        status=status, completion_status=completion,
    )


def test_same_host_distinct_paths_produce_advisory_not_page_level_trends():
    a = _candidate("AUD-ONE", "https://shop.example.org/produto-a")
    b = _candidate("AUD-TWO", "https://shop.example.org/produto-b",
                   timestamp="2026-10-09T08:00:00-03:00")
    result = preview_same_domain_candidates((b, a))
    assert result["eligible"] is True
    assert result["hostname"] == "shop.example.org"
    assert result["device"] == "MOBILE"
    assert result["comparison_mode"] == "SAME_DOMAIN_COMPARATIVE"
    assert result["url_universe_count"] == 2
    assert [x["audit_id"] for x in result["audits"]] == ["AUD-ONE", "AUD-TWO"]
    assert result["audits"][0]["observed_at_utc"] == "2026-10-09T10:00:00+00:00"
    assert result["audits"][1]["observed_at_utc"] == "2026-10-09T11:00:00+00:00"
    assert result["audits"][0]["url_universe_fingerprint"] != (
        result["audits"][1]["url_universe_fingerprint"]
    )
    assert all(x["page_metrics_comparison"] == "N/D" for x in result["audits"])
    assert all(x["score_delta"] is None for x in result["audits"])
    assert result["page_level_trends_eligible"] is False
    assert result["audit_score_deltas_eligible"] is False
    assert result["apdex_or_cwv_deltas_eligible"] is False
    assert result["production_cons_mode_changed"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0


def test_same_url_must_remain_in_strict_longitudinal_mode():
    a = _candidate("AUD-ONE", "https://example.org/seguro")
    b = _candidate("AUD-TWO", "https://example.org/seguro")
    result = preview_same_domain_candidates((a, b))
    assert not result["eligible"]
    assert result["reason"] == "SAME_URL_USE_STRICT_LONGITUDINAL_MODE"


def test_different_hosts_do_not_blend_www_subdomains_or_sibling_domains():
    first = _candidate("AUD-ONE", "https://www.example.org/a")
    candidates = [
        _candidate("AUD-TWO", "https://example.org/b"),
        _candidate("AUD-TWO", "https://api.example.org/b"),
        _candidate("AUD-TWO", "https://different.org/b"),
    ]
    for second in candidates:
        result = preview_same_domain_candidates((first, second))
        assert not result["eligible"]
        assert result["reason"] == "DIFFERENT_HOSTNAMES"


def test_mixed_devices_and_noncomplete_aud_fail_closed():
    first = _candidate("AUD-ONE", "https://example.org/a")
    second = _candidate("AUD-TWO", "https://example.org/b", device="DESKTOP")
    assert preview_same_domain_candidates((first, second))["reason"] == (
        "INCOMPATIBLE_DEVICE"
    )
    assert preview_same_domain_candidates(
        (first, replace(second, device="MOBILE", completion_status="PARTIAL_RETRYABLE"))
    )["reason"] == "AUD_NOT_LOGICALLY_COMPLETE"
    assert preview_same_domain_candidates(
        (first, replace(second, device="MOBILE", status="FAILED"))
    )["reason"] == "AUD_NOT_LOGICALLY_COMPLETE"


def test_untrusted_clock_tie_and_duplicates_never_create_time_delta():
    first = _candidate("AUD-ONE", "https://example.org/a")
    second = _candidate("AUD-TWO", "https://example.org/b")
    assert preview_same_domain_candidates((first, second))["reason"] == (
        "UNVERIFIABLE_OBSERVATION_CHRONOLOGY"
    )
    assert preview_same_domain_candidates((
        first, replace(second, event_time="2026-10-09T10:00:00"),
    ))["reason"] == "UNVERIFIABLE_OBSERVATION_CHRONOLOGY"
    assert preview_same_domain_candidates((
        first, replace(second, event_time="2026-10-09T07:00:00-03:00"),
    ))["reason"] == "UNVERIFIABLE_OBSERVATION_CHRONOLOGY"
    assert preview_same_domain_candidates((
        first, replace(second, audit_id=first.audit_id),
    ))["reason"] == "INVALID_OR_DUPLICATE_AUD_ID"


def test_invalid_unsafe_urls_and_count_limits_fail_closed():
    a = _candidate("AUD-ONE", "https://example.org/a")
    for address in (
        "file:///etc/passwd", "https://user:secret@example.org/b",
        "https://127.0.0.1/b", "http://localhost/b",
        "https://example.org:99999/b", "",
    ):
        result = preview_same_domain_candidates((
            a, _candidate("AUD-TWO", address,
                          timestamp="2026-10-09T11:00:00+00:00"),
        ))
        assert not result["eligible"]
        assert result["reason"] == "UNVERIFIABLE_SINGLE_URL"
    assert preview_same_domain_candidates((a,))["reason"] == "AUDIT_COUNT_OUT_OF_RANGE"
    assert preview_same_domain_candidates((a,) * 101)["reason"] == "AUDIT_COUNT_OUT_OF_RANGE"


def test_no_external_call_or_materialization_imported():
    from rasai.consolidation import domain_comparative_preview_210 as module
    assert not any(name in module.__dict__ for name in (
        "requests", "httpx", "sqlite3", "AuditWorkspace", "materialize_geo_observation",
    ))


def test_padded_control_or_backslash_url_cannot_become_verified_domain_source():
    a = _candidate("AUD-ONE", "https://example.org/a")
    bad_urls = (
        " https://example.org/b",
        "https://example.org/b ",
        "https://example.org/b\n",
        "https://example.org/b\t",
        "https://example.org/b\r",
        "https://example.org/b\x7f",
        "https://example.org\\\\b",
    )
    for url in bad_urls:
        other = _candidate("AUD-TWO", url, timestamp="2026-10-09T11:00:00Z")
        result = preview_same_domain_candidates((a, other))
        assert result["reason"] == "UNVERIFIABLE_SINGLE_URL", repr(url)
        assert result["eligible"] is False
        assert result["audit_writes"] == result["provider_requests"] == 0


def test_hash_routed_spa_urls_never_collapse_into_same_page_universe():
    """#210: hash fragments can select distinct client-rendered screens."""
    plain = _candidate("AUD-ONE", "https://shop.example.org/app")
    for fragment in (
        "https://shop.example.org/app#/produto-a",
        "https://shop.example.org/app#/produto-b",
        "https://shop.example.org/app#",
        "https://shop.example.org/app#section-one",
    ):
        candidate = _candidate(
            "AUD-TWO", fragment, timestamp="2026-10-09T11:00:00Z",
        )
        output = preview_same_domain_candidates((plain, candidate))
        assert output["eligible"] is False
        assert output["reason"] == "UNVERIFIABLE_SINGLE_URL"
        assert output["audits"] == []
        assert output["page_level_trends_eligible"] is False
        assert output["audit_score_deltas_eligible"] is False
        assert output["apdex_or_cwv_deltas_eligible"] is False
        assert output["provider_requests"] == output["audit_writes"] == 0

    # Two different SPA fragment routes cannot be silently coerced to
    # the exact same URL and referred to the strict CONS longitudinal path.
    a = _candidate("AUD-ONE", "https://shop.example.org/app#/a")
    b = _candidate("AUD-TWO", "https://shop.example.org/app#/b",
                   timestamp="2026-10-09T11:00:00Z")
    outcome = preview_same_domain_candidates((a, b))
    assert outcome["reason"] == "UNVERIFIABLE_SINGLE_URL"
    # Encoded "#" in the actual URL query is not a fragment.
    a = _candidate("AUD-ONE", "https://shop.example.org/app?tab=%23a")
    b = _candidate("AUD-TWO", "https://shop.example.org/app?tab=%23b",
                   timestamp="2026-10-09T11:00:00Z")
    assert preview_same_domain_candidates((a, b))["eligible"] is True


def test_same_hostname_mixed_http_origins_abstain_without_score_claim():
    first = _candidate("AUD-ONE", "https://example.org/seguro")
    for different_origin in (
        "http://example.org/vida",
        "https://example.org:8443/vida",
        "http://example.org:8080/vida",
    ):
        second = _candidate(
            "AUD-TWO", different_origin,
            timestamp="2026-10-09T11:00:00Z",
        )
        value = preview_same_domain_candidates((first, second))
        assert value["eligible"] is False
        assert value["reason"] == "DIFFERENT_URL_ORIGINS_UNVERIFIED"
        assert value["origin"] is None and value["audits"] == []
        assert value["audit_score_deltas_eligible"] is False
        assert value["apdex_or_cwv_deltas_eligible"] is False
        assert value["provider_requests"] == value["audit_writes"] == 0


def test_default_https_port_normalizes_to_same_origin_without_score_delta():
    a = _candidate("AUD-ONE", "https://example.org:443/a")
    b = _candidate(
        "AUD-TWO", "https://example.org/b",
        timestamp="2026-10-09T11:00:00Z",
    )
    out = preview_same_domain_candidates((a, b))
    assert out["eligible"] is True
    assert out["hostname"] == "example.org"
    assert out["origin"] == "https://example.org"
    assert out["audits"][0]["url"] == "https://example.org/a"
    assert out["url_universe_count"] == 2
    assert out["page_level_trends_eligible"] is False


def test_two_urls_same_explicit_nondefault_https_port_remain_advisory():
    a = _candidate("AUD-ONE", "https://example.org:8443/a")
    b = _candidate(
        "AUD-TWO", "https://example.org:8443/b",
        timestamp="2026-10-09T11:00:00Z",
    )
    out = preview_same_domain_candidates((a, b))
    assert out["eligible"] is True
    assert out["origin"] == "https://example.org:8443"
    assert out["audit_score_deltas_eligible"] is False

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

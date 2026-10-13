"""#210 domain feasibility is pure, nonexecuting, and never a cross-URL trend."""
from __future__ import annotations

from dataclasses import replace
import pytest

from rasai.consolidation.selection import AuditCandidate
from rasai.consolidation.domain_preflight_210 import assess_same_domain_pair


def candidate(audit_id, url, *, device="MOBILE", time="2026-10-08T11:00:00Z"):
    return AuditCandidate(
        audit_id=audit_id,
        event_time=time,
        url=url,
        domain="not-trusted-from-index-alone",
        device=device,
        status="COMPLETED",
        completion_status="COMPLETE",
    )


def test_same_host_distinct_paths_produces_only_explicit_descriptive_review():
    a = candidate("AUD-A", "https://www.example.org/product-a")
    b = candidate(
        "AUD-B", "https://WWW.EXAMPLE.ORG./product-b",
        time="2026-10-09T12:00:00+01:00",
    )
    result = assess_same_domain_pair(a, b)
    assert result["status"] == "ELIGIBLE_FOR_DESCRIPTIVE_SAME_HOST_REVIEW_ONLY"
    assert result["mode"] == "SAME_DOMAIN_DESCRIPTIVE_PREVIEW_ONLY"
    assert result["reason"] == "NO_CROSS_URL_LONGITUDINAL_INFERENCE"
    assert result["metric_comparability"]["scores"] == (
        "NOT_COMPARABLE_DIFFERENT_URL_UNIVERSES"
    )
    assert result["metric_comparability"]["web_performance"] == (
        "PER_URL_ONLY_NO_CROSS_URL_DELTA"
    )
    assert result["metric_comparability"]["synthetic_apdex"] == (
        "PER_URL_AND_PROFILE_ONLY_NO_CROSS_URL_TREND"
    )
    assert not result["audit_score_trend_allowed"]
    assert not result["page_level_deltas_allowed"]
    assert not result["metric_comparison_executed"]
    assert not result["new_cons_generated"]
    assert not result["source_attestation_verified"]
    assert not result["same_url_longitudinal_changed"]
    assert not result["registrable_domain_equivalence_claimed"]
    assert result["source_audit_writes"] == result["provider_requests"] == 0


@pytest.mark.parametrize(
    ("changed_url", "reason"),
    [
        ("https://other.org/product-b", "EXACT_HOST_MISMATCH"),
        ("https://sub.example.org/product-b", "EXACT_HOST_MISMATCH"),
        ("http://www.example.org/product-b", "DIFFERENT_SCHEME_OR_PORT"),
        ("https://www.example.org:8443/product-b", "DIFFERENT_SCHEME_OR_PORT"),
        ("https://www.example.org/product-a", "SAME_URL_USE_EXISTING_LONGITUDINAL_CONS"),
        ("file:///etc/passwd", "SINGLE_URL_ORIGIN_INVALID"),
        ("https://account:secret@www.example.org/product-b", "SINGLE_URL_ORIGIN_INVALID"),
        ("https://localhost/product-b", "SINGLE_URL_ORIGIN_INVALID"),
    ],
)
def test_scope_guards_block_same_org_inferences(changed_url, reason):
    a = candidate("AUD-A", "https://www.example.org/product-a")
    b = candidate("AUD-B", changed_url, time="2026-10-09T12:00:00Z")
    review = assess_same_domain_pair(a, b)
    assert review["status"] == "NOT_ELIGIBLE"
    assert review["reason"] == reason
    assert review["source_audit_writes"] == review["provider_requests"] == 0
    assert not review["page_level_deltas_allowed"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"device": "DESKTOP"}, "DEVICE_MISMATCH"),
        ({"device": "TABLET"}, "DEVICE_MISMATCH"),
        ({"status": "RUNNING"}, "SOURCE_AUD_NOT_COMPLETE"),
        ({"completion_status": "PARTIAL_RETRYABLE"}, "SOURCE_AUD_NOT_COMPLETE"),
        ({"event_time": "not-a-date"}, "CHRONOLOGY_UNVERIFIABLE"),
        ({"event_time": "2026-10-08T11:00:00"}, "CHRONOLOGY_UNVERIFIABLE"),
        ({"event_time": "2026-10-08T11:00:00+00:00"}, "CHRONOLOGY_NOT_ORDERABLE"),
        ({"audit_id": "AUD-A"}, "DISTINCT_AUD_IDS_REQUIRED"),
    ],
)
def test_evidence_and_context_must_not_be_assumed(changes, reason):
    a = candidate("AUD-A", "https://www.example.org/a")
    b = replace(
        candidate("AUD-B", "https://www.example.org/b",
                  time="2026-10-09T12:00:00Z"),
        **changes,
    )
    result = assess_same_domain_pair(a, b)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == reason


def test_pair_comparability_does_not_reuse_candidate_declared_domain():
    a = candidate("AUD-A", "https://a.example.org/a")
    b = candidate("AUD-B", "https://b.example.org/b",
                  time="2026-10-09T12:00:00Z")
    assert a.domain == b.domain == "not-trusted-from-index-alone"
    review = assess_same_domain_pair(a, b)
    assert review["reason"] == "EXACT_HOST_MISMATCH"
    assert "AUD-A" not in str(review)
    assert "AUD-B" not in str(review)


def test_equal_origin_with_explicit_standard_https_port_can_be_reviewed():
    a = candidate("AUD-A", "https://www.example.org/a")
    b = candidate("AUD-B", "https://www.example.org:443/b",
                  time="2026-10-09T12:00:00Z")
    assert assess_same_domain_pair(a, b)["status"] == (
        "ELIGIBLE_FOR_DESCRIPTIVE_SAME_HOST_REVIEW_ONLY"
    )

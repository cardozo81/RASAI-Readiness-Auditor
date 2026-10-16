"""#210 domain feasibility is pure, nonexecuting, and never a cross-URL trend."""
from __future__ import annotations

from dataclasses import replace
import pytest

from rasai.consolidation.selection import AuditCandidate
from rasai.consolidation.domain_preflight import assess_same_domain_pair


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
        ({"device": "TABLET"}, "DEVICE_NOT_PROVEN"),
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


@pytest.mark.parametrize(
    "candidate_url",
    [
        "https://www.example.org/product-a#reviews",
        "https://www.example.org:443/product-a#section",
        "https://WWW.EXAMPLE.ORG./product-a#other",
    ],
)
def test_html_fragments_do_not_create_independent_page_universes(candidate_url):
    a = candidate("AUD-A", "https://www.example.org/product-a")
    b = candidate("AUD-B", candidate_url, time="2026-10-09T12:00:00Z")
    result = assess_same_domain_pair(a, b)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == "SAME_URL_USE_EXISTING_LONGITUDINAL_CONS"


def test_incorrect_python_types_in_source_candidate_fail_closed():
    a = candidate("AUD-A", "https://www.example.org/product-a")
    b = replace(candidate("AUD-B", "https://www.example.org/product-b",
                          time="2026-10-09T12:00:00Z"), device=None)
    assert assess_same_domain_pair(a, b)["reason"] == "DEVICE_NOT_PROVEN"
    assert assess_same_domain_pair(a, None)["reason"] == "CANDIDATE_SOURCE_NOT_PROVEN"
    wrong_status = replace(b, device="MOBILE", status=None)
    assert assess_same_domain_pair(a, wrong_status)["reason"] == "SOURCE_AUD_NOT_COMPLETE"


def test_aware_offsets_same_absolute_instant_are_not_a_chronological_pair():
    a = candidate("AUD-A", "https://www.example.org/product-a")
    b = candidate("AUD-B", "https://www.example.org/product-b",
                  time="2026-10-08T08:00:00-03:00")
    assert assess_same_domain_pair(a, b)["reason"] == "CHRONOLOGY_NOT_ORDERABLE"


@pytest.mark.parametrize(
    ("older_url", "newer_url"),
    [
        ("https://example.org/app#/products/a", "https://example.org/app#/products/b"),
        ("https://example.org/app#!/products/a", "https://example.org/app#!/products/b"),
        ("https://example.org/app#overview", "https://example.org/app#/products/b"),
        ("https://example.org/app#overview", "https://example.org/app#!/products/b"),
    ],
)
def test_spa_hash_routes_are_distinct_page_universes_without_content_claims(
    older_url, newer_url,
):
    first = candidate("AUD-SPA1", older_url)
    second = candidate("AUD-SPA2", newer_url, time="2026-10-09T12:00:00Z")
    result = assess_same_domain_pair(first, second)
    assert result["status"] == "ELIGIBLE_FOR_DESCRIPTIVE_SAME_HOST_REVIEW_ONLY"
    assert result["reason"] == "NO_CROSS_URL_LONGITUDINAL_INFERENCE"
    assert result["page_level_deltas_allowed"] is False
    assert result["audit_score_trend_allowed"] is False
    assert result["source_attestation_verified"] is False
    assert result["provider_requests"] == result["source_audit_writes"] == 0


@pytest.mark.parametrize(
    ("older_url", "newer_url"),
    [
        ("https://example.org/app#/products/a", "https://example.org/app#/products/a"),
        ("https://example.org/app#!/products/a", "https://example.org/app#!/products/a"),
        ("https://example.org/app#section1", "https://example.org/app#section2"),
        ("https://example.org/app#section1", "https://example.org/app"),
    ],
)
def test_same_spa_route_or_ordinary_fragment_never_count_as_distinct_pages(
    older_url, newer_url,
):
    a = candidate("AUD-SPA1", older_url)
    b = candidate("AUD-SPA2", newer_url, time="2026-10-09T12:00:00Z")
    result = assess_same_domain_pair(a, b)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == "SAME_URL_USE_EXISTING_LONGITUDINAL_CONS"


@pytest.mark.parametrize("untrusted_url", [
    " https://example.org/new",
    "https://example.org/new ",
    "https://example.org/pa\\th",
    "https://example.org/new\tstep",
    "https://example.org/new\nstep",
    "https://example.org/new\rstep",
    "https://example.org/new\x00",
    "https://example.org:443\\@evil.example/new",
    "https://example.org%2Eevil.example/new",
    "https://user@example.org/new",
    "https://example.org/new#section\x7f",
    "https://example.org/" + "a" * 2100,
])
def test_preflight_rejects_ambiguous_url_before_urlsplit_normalization(untrusted_url):
    first = candidate("AUD-ORIGIN", "https://example.org/old")
    second = candidate("AUD-NEW", untrusted_url, time="2026-10-09T12:00:00Z")
    result = assess_same_domain_pair(first, second)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == "SINGLE_URL_ORIGIN_INVALID"
    assert result["metric_comparison_executed"] is False
    assert result["new_cons_generated"] is False
    assert result["provider_requests"] == result["source_audit_writes"] == 0


class _AuthorizedIndexFixture:
    def __init__(self):
        self.urls = {
            "AUD-REFERENCE": "https://example.org/service-a",
            "AUD-ELIGIBLE": "https://example.org/service-b",
            "AUD-FOREIGN": "https://another.example.org/service-b",
            "AUD-NO-CONSENT": "https://example.org/private-offer",
        }
        self.read_calls = []

    def candidate_audits(self, filters):
        allowed = tuple(filters.audit_ids or ())
        self.read_calls.append(("candidates", allowed))
        return tuple(
            {
                "audit_id": audit_id, "url_count": 1,
                "devices_json": '["MOBILE"]',
                "status": "COMPLETED", "completion_status": "COMPLETE",
                "event_time": f"2026-10-{10+index:02d}T11:00:00Z",
            }
            for index, audit_id in enumerate(self.urls)
            if audit_id in allowed
        )

    def available_urls(self, filters):
        audit_id, = filters.audit_ids
        self.read_calls.append(("urls", audit_id))
        return (self.urls[audit_id],)


def test_same_host_candidate_discovery_requires_explicit_authorized_index_scope():
    from rasai.consolidation.domain_preflight import (
        preview_authorized_same_host_candidates,
    )

    index = _AuthorizedIndexFixture()
    result = preview_authorized_same_host_candidates(
        index,
        reference_audit_id="AUD-REFERENCE",
        allowed_audit_ids=("AUD-REFERENCE", "AUD-ELIGIBLE", "AUD-FOREIGN"),
    )
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["audit_id"] == "AUD-ELIGIBLE"
    assert result["candidates"][0]["url"] == "https://example.org/service-b"
    assert result["candidates"][0]["metric_comparability"]["scores"] == (
        "NOT_COMPARABLE_DIFFERENT_URL_UNIVERSES"
    )
    assert not result["cross_url_scoring_allowed"]
    assert not result["new_cons_generated"]
    assert not result["source_attestation_verified"]
    assert result["provider_requests"] == result["source_audit_writes"] == 0
    assert result["same_url_selection_unchanged"]
    assert ("candidates", ("AUD-REFERENCE", "AUD-ELIGIBLE", "AUD-FOREIGN")) in index.read_calls
    assert not any("AUD-NO-CONSENT" in str(call) for call in index.read_calls)


def test_same_host_candidate_discovery_fails_closed_on_unbounded_scope():
    from rasai.consolidation.domain_preflight import (
        preview_authorized_same_host_candidates as preview,
    )

    index = _AuthorizedIndexFixture()
    with pytest.raises(ValueError, match="authorization"):
        preview(index, reference_audit_id="AUD-REFERENCE", allowed_audit_ids=())
    with pytest.raises(ValueError, match="authorization"):
        preview(index, reference_audit_id="AUD-REFERENCE",
                allowed_audit_ids=("AUD-ELIGIBLE",))
    with pytest.raises(ValueError, match="authorization"):
        preview(index, reference_audit_id="AUD-REFERENCE",
                allowed_audit_ids=("AUD-REFERENCE", "AUD-ELIGIBLE"),
                max_candidates=0)
    with pytest.raises(ValueError, match="reference AUD"):
        preview(index, reference_audit_id="AUD-MISSING",
                allowed_audit_ids=("AUD-MISSING", "AUD-ELIGIBLE"))
    assert index.read_calls == [
        ("candidates", ("AUD-MISSING", "AUD-ELIGIBLE")),
        ("urls", "AUD-ELIGIBLE"),
    ]

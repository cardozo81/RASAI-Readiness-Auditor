"""Synthetic offline contextual discovery contracts."""
from datetime import datetime, timezone

import pytest

from rasai.contextual_documents import DiscoveryLimits, discover_references
from rasai.domain import DeviceContext, PageSnapshot


def snapshot(**kw):
    values = dict(snapshot_id="SNP-fixture", page_id="PGE-fixture", device=DeviceContext.MOBILE,
                  requested_url="https://example.test/start", final_url="https://example.test/product/",
                  captured_at=datetime(2026, 11, 10, tzinfo=timezone.utc))
    return PageSnapshot(**(values | kw))


def discover(html=b"", **kw):
    return discover_references(audit_id="AUD-fixture", snapshot=snapshot(), original=html,
                               artifact_ref="artifacts/page.html", surface="RAW_HTML_FALLBACK", **kw)


@pytest.mark.parametrize("href,resolved,policy", [
    ("../terms.pdf", "https://example.test/terms.pdf", "REFERENCE_ONLY_NO_EGRESS"),
    ("https://example.test/terms.pdf", "https://example.test/terms.pdf", "REFERENCE_ONLY_NO_EGRESS"),
    ("#terms", None, "INVALID_REFERENCE"),
    ("javascript:alert(1)", None, "INVALID_REFERENCE"),
    ("data:text/html,x", None, "INVALID_REFERENCE"),
    ("https://[broken", None, "INVALID_REFERENCE"),
    ("https://127.0.0.1/a", "https://127.0.0.1/a", "UNSAFE_ADDRESS"),
    ("https://other.test/a", "https://other.test/a", "CROSS_ORIGIN_NOT_AUTHORIZED"),
])
def test_reference_policy(href, resolved, policy):
    row = discover(f'<a href="{href}">Conditions</a>'.encode())["occurrences"][0]
    assert (row["resolved_url"], row["url_policy"]) == (resolved, policy)
    assert row["document_final_url_observed"] is None


def test_duplicate_identity_context_and_spa_unknown():
    data = b'<p>Contract Alpha <a href="/terms">Conditions</a> end</p><a href="/terms">Conditions</a>'
    first = discover(data)
    assert first == discover(data)
    links = [x for x in first["occurrences"] if x["kind"] == "ANCHOR"]
    assert len(links) == 2
    assert links[0]["occurrence_id"] != links[1]["occurrence_id"]
    assert links[0]["document_candidate_id"] == links[1]["document_candidate_id"]
    assert "Contract Alpha" in links[0]["context"]
    assert "LATE_SPA_REFERENCES_NOT_CAPTURED_ND" in first["limitations"]
    assert all(x["applicability"] == "INSUFFICIENT_EVIDENCE" for x in links)


def test_limits_and_uncaptured():
    assert discover(b"xxx", limits=DiscoveryLimits(max_bytes=2))["limitations"][-1] == "SOURCE_BYTE_LIMIT_ND"
    result = discover(b'<a href="/a">a</a><a href="/b">b</a>', limits=DiscoveryLimits(max_occurrences=1))
    assert len(result["occurrences"]) == 1
    assert "OCCURRENCE_LIMIT_PARTIAL" in result["limitations"]

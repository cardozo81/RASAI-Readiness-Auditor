from datetime import datetime, timezone
import sqlite3

import pytest

from rasai.contextual_search import correlate_persisted
from tests.test_geo_query_ledger import _audit
from tests.test_contextual_content import observed
from tests.test_contextual_advisory import offline  # shared egress tripwire


def capture():
    item = observed('<main><p>Produto seguro de vida.</p></main>')
    item["audit_id"] = "AUD-GEO304"
    item["captured_at"] = "2026-10-10T12:00:00Z"
    item["requested_url"] = item["final_url_observed"] = "https://example.org/shared"
    item["device"] = "mobile"
    return item


def test_same_query_scope_and_period_descriptive_url_match_never_contextual_proof(tmp_path):
    root = _audit(tmp_path, multi=False)
    result = correlate_persisted(root, [capture()])
    row = result["observations"][0]
    assert result["status"] == "NOT_COMPARABLE"
    assert row["status"] == "DESCRIPTIVE_ONLY"
    assert row["alignment"]["status"] == "QUERY_MATCH"
    assert row["exact_url_observations"] == [dict(serp_distinct_urls=3, external_distinct_urls=2, common_urls=1)]
    assert row["source_run_ids"] == ["PX-A"] and row["evidence_ids"] == ["SERP-0"]
    assert row["local_references"][0]["exact_page_url_in_serp"] is True
    assert row["local_references"][0]["contextual_status"] == "NOT_COMPARABLE"
    assert "EXTERNAL_CONTEXT_EQUIVALENCE_UNPROVEN" in row["local_references"][0]["reasons"]
    assert result["provider_calls"] == 0


@pytest.mark.parametrize("mutation,reason", [
    ("UPDATE serp_observations SET query='diferente'", "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"),
    ("DELETE FROM serp_observations", "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"),
    ("DELETE FROM perplexity_search_runs", "EXTERNAL_SEARCH_NOT_FOUND"),
    ("UPDATE perplexity_search_runs SET status='FAILED'", "EXTERNAL_SEARCH_NOT_SUCCESSFUL"),
    ("UPDATE perplexity_search_runs SET started_at='2020-01-01T00:00:00Z'", "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"),
    ("UPDATE perplexity_search_runs SET audit_id='AUD-FOREIGN'", "EXTERNAL_SEARCH_NOT_FOUND"),
    ("UPDATE perplexity_search_sources SET url='javascript:alert(1)'", "NO_VALID_EXTERNAL_URL_DENOMINATOR"),
])
def test_incompatible_missing_failed_old_foreign_and_malformed_sources_abstain(tmp_path, mutation, reason):
    root = _audit(tmp_path, multi=False)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(mutation)
    result = correlate_persisted(root, [capture()])
    assert result["status"] == "NOT_COMPARABLE"
    assert reason in {result["reason"], *(r["reason"] for r in result["observations"])}
    assert all(not r["exact_url_observations"] for r in result["observations"])


def test_multiquery_without_attribution_and_device_mismatch(tmp_path):
    root = _audit(tmp_path, multi=True, source_query_column=False)
    result = correlate_persisted(root, [capture()])
    assert all(r["reason"] == "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN" for r in result["observations"])


def test_same_query_different_device_period_and_exact_host_are_separate(tmp_path):
    root = _audit(tmp_path, multi=False)
    item = capture()
    item["device"] = "desktop"
    item["captured_at"] = "2020-01-01T00:00:00Z"
    item["final_url_observed"] = "https://example.org/different-page"
    row = correlate_persisted(root, [item])["observations"][0]["local_references"][0]
    assert row["exact_page_url_in_serp"] is False
    assert "CAPTURE_SERP_DEVICE_MISMATCH_ND" in row["reasons"]
    assert "CAPTURE_SEARCH_WINDOW_MISMATCH_ND" in row["reasons"]


def test_same_aud_only_selection(tmp_path):
    root = _audit(tmp_path, multi=False)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE serp_observations SET audit_id='AUD-FOREIGN'")
    result = correlate_persisted(root, [capture()])
    assert all(not r["local_references"] for r in result["observations"])


def test_foreign_capture_is_never_correlated(tmp_path):
    root = _audit(tmp_path, multi=False)
    item = capture()
    item["audit_id"] = "AUD-FOREIGN"
    row = correlate_persisted(root, [item])["observations"][0]
    assert row["local_references"] == []
    assert "FOREIGN_CAPTURE_NOT_CORRELATED" in row["limitations"]

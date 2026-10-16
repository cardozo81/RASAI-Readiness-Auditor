"""Read-only optional SEO evidence must abstain on acquisition failures."""
import json

import pytest

from rasai.optional_seo_policy import classify_seo_evidence


@pytest.mark.parametrize(
    ("rule_id", "evidence"),
    [
        ("BR-GEO-003", {"sitemaps": [{"state": "ABSENT"}]}),
        ("BR-GEO-013", {"canonicals": []}),
        ("BR-GEO-017", {"state": "ABSENT"}),
    ],
)
def test_acquisition_error_is_not_optional_absence(rule_id: str, evidence: dict) -> None:
    assert classify_seo_evidence(rule_id, evidence) == "OPTIONAL_ABSENCE"
    failed = {**evidence, "error": "NETWORK_TIMEOUT"}
    assert classify_seo_evidence(rule_id, failed) == "UNKNOWN"
    assert classify_seo_evidence(rule_id, json.dumps(failed)) == "UNKNOWN"


def test_duplicate_json_keys_are_not_evidence() -> None:
    assert classify_seo_evidence(
        "BR-GEO-013", '{"canonicals":[],"canonicals":[]}'
    ) == "UNKNOWN"

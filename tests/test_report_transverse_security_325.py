"""#325: real-smoke regression for JSON-serialized DOM selector evidence."""
from __future__ import annotations

from html import escape

import pytest

from rasai.catalog_report_assurance import _credential_output_failures
from rasai.secret_safety import detect_secret_exposures


SEMANTIC_ID = "sk-LIFEShowcaseProcessUIDef-Covers-Fieldset3-PanelGroup1-panel_content_2"
SCOPED_TOKEN = "sk-proj-ABCD1234efgh5678IJKL9012mnop3456"
OPAQUE_TOKEN = "sk-abcdefghijklmnopqrstuvwxyz1234567890AB"


@pytest.mark.parametrize(
    "structured_evidence",
    [
        '{"href": "#' + SEMANTIC_ID + '"}',
        r'{\"href\": \"#' + SEMANTIC_ID + r'\"}',
        '{"href": "https://example.test/page#' + SEMANTIC_ID + '"}',
        r'{\"href\": \"https://example.test/page#' + SEMANTIC_ID + r'\"}',
        '{"selector": "div#' + SEMANTIC_ID + '"}',
        r'{\"selector\": \"div#' + SEMANTIC_ID + r'\"}',
    ],
)
def test_transverse_assurance_accepts_proven_dom_fragments_in_json_evidence(
    structured_evidence: str,
) -> None:
    report_html = "<pre>" + escape(structured_evidence) + "</pre>"
    assert _credential_output_failures(report_html) == []
    assert detect_secret_exposures(
        structured_evidence,
        path="catalog-report.html",
        strict=True,
        html_dom_context=False,
    )


@pytest.mark.parametrize("candidate", [SCOPED_TOKEN, OPAQUE_TOKEN])
@pytest.mark.parametrize("field", ["href", "selector"])
@pytest.mark.parametrize("escaped_json", [False, True])
def test_transverse_assurance_blocks_realistic_tokens_even_in_json_fragments(
    candidate: str, field: str, escaped_json: bool,
) -> None:
    value = "https://example.test/page#" + candidate if field == "href" else "div#" + candidate
    evidence = '{"' + field + '": "' + value + '"}'
    if escaped_json:
        evidence = evidence.replace('"', r'\"')
    assert _credential_output_failures("<pre>" + escape(evidence) + "</pre>")


@pytest.mark.parametrize(
    "unsafe",
    [
        "Arbitrary prose #" + SEMANTIC_ID,
        "Authorization: Bearer deliberately-secret-12345",
        "api_key='unsafe-secret-for-test-123'",
        "postgresql://test:opaque-test-password-123@localhost/database",
    ],
)
def test_transverse_assurance_remains_fail_closed_without_evidence_context(
    unsafe: str,
) -> None:
    assert _credential_output_failures("<pre>" + escape(unsafe) + "</pre>")

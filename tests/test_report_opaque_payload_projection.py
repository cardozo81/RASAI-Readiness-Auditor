"""Regression: report-only omission of opaque OpenAI payloads (AUD-CD169).

No network, provider, mutable audit operation or security-detector relaxation.
"""
import json
from hashlib import sha256
from html import escape

from rasai.catalog_report_assurance import _credential_output_failures
from rasai.catalog_report_integrations import _raw_payload_block
from rasai.parallel_report.sanitization import sanitize
from rasai.report_opaque_projection import (
    OPAQUE_STATUS,
    UNPARSEABLE_STATUS,
    opaque_metadata,
    project_opaque_fields,
)

OPAQUE = "ghp_" + "A" * 38
OTHER_SECRET = "ghp_" + "B" * 38


def test_catalog_omits_only_opaque_bytes_and_preserves_canonical_db_evidence():
    source = json.dumps({
        "output": [
            {"type": "reasoning", "encrypted_content": OPAQUE, "id": "item-3"},
            {"type": "message", "text": "Resposta preservada"},
        ],
    }, ensure_ascii=False)
    html = _raw_payload_block(source)
    assert OPAQUE not in html
    assert OPAQUE_STATUS in html
    assert "item-3" in html and "Resposta preservada" in html
    assert _credential_output_failures(html) == []
    assert json.loads(source)["output"][0]["encrypted_content"] == OPAQUE
    assert _credential_output_failures(_raw_payload_block(json.dumps({"message": OTHER_SECRET})))


def test_opaque_metadata_size_hash_and_nested_json_are_stable():
    nested = json.dumps({"output": [{"encrypted_content": OPAQUE, "status": "ok"}]})
    projected = project_opaque_fields({"response_payload": nested, "provider": "OPENAI"})
    value = json.loads(projected["response_payload"])["output"][0]["encrypted_content"]
    assert value == opaque_metadata(OPAQUE)
    assert value["sha256"] == sha256(OPAQUE.encode("utf-8")).hexdigest()
    assert value["size_bytes"] == len(OPAQUE.encode("utf-8"))
    assert projected["provider"] == "OPENAI"
    assert project_opaque_fields("plain JSON absent") == "plain JSON absent"


def test_presentation_omits_in_records_and_json_annex_and_preserves_unrelated_data():
    source = {"response_payload": json.dumps({
        "output": [{"type": "reasoning", "encrypted_content": OPAQUE}],
        "usage": {"output_tokens": 0},
    }), "provider": "OPENAI"}
    clean = sanitize(source)
    assert OPAQUE not in json.dumps(clean)
    assert clean["response_payload"]["output"][0]["encrypted_content"]["status"] == OPAQUE_STATUS
    assert clean["response_payload"]["usage"]["output_tokens"] == 0
    assert clean["provider"] == "OPENAI"


def test_invalid_json_opaque_fails_closed_without_suppressing_real_secret_detection():
    source = '{"output":[{"encrypted_content":"' + OPAQUE + '"}'  # deliberately invalid
    assert project_opaque_fields(source) == UNPARSEABLE_STATUS
    assert sanitize({"response_payload": source})["response_payload"] == UNPARSEABLE_STATUS
    assert _credential_output_failures("<pre>" + escape(OTHER_SECRET) + "</pre>")

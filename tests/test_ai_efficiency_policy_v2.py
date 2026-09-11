from __future__ import annotations

from rasai.ai_efficiency_policy import _compact_semantic_provider_payload


def test_compaction_removes_only_duplicate_or_local_transport_fields() -> None:
    payload = {
        "snapshot_id": "SNP-1",
        "page_url": "https://example.test/",
        "title": "Example",
        "main_content": "complete page content",
        "structured_data": {"blocks": [{"types": ["Organization"]}]},
        "primary_language": "pt-BR",
        "market": "BR",
        "evidence": [
            {
                "evidence_id": "EV-CONTEXT",
                "evidence_type": "TEXT_EXCERPT",
                "source": "semantic-input-builder",
                "observed_value": {
                    "title": "Example",
                    "main_content_excerpt": "complete page content",
                    "main_content_available": True,
                    "structured_data_available": True,
                },
                "artifact_reference": "artifacts/extraction/main_content.txt",
            },
            {
                "evidence_id": "EV-OTHER",
                "evidence_type": "DOM_ELEMENT",
                "source": "m4",
                "observed_value": {"heading": "Preserve me"},
                "artifact_reference": "artifacts/rendered/page.html",
            },
        ],
    }

    compact = _compact_semantic_provider_payload(payload)

    assert compact["main_content"] == payload["main_content"]
    assert compact["structured_data"] == payload["structured_data"]
    assert compact["title"] == payload["title"]
    assert compact["evidence"][0]["evidence_id"] == "EV-CONTEXT"
    assert compact["evidence"][0]["observed_value"] == {
        "main_content_available": True,
        "structured_data_available": True,
    }
    assert "artifact_reference" not in compact["evidence"][0]
    assert compact["evidence"][1]["observed_value"] == {"heading": "Preserve me"}
    assert "artifact_reference" not in compact["evidence"][1]


def test_compaction_does_not_mutate_original_payload() -> None:
    payload = {
        "main_content": "content",
        "structured_data": None,
        "evidence": [
            {
                "evidence_id": "EV-1",
                "source": "other",
                "observed_value": {"value": "x"},
                "artifact_reference": "local-only.txt",
            }
        ],
    }

    compact = _compact_semantic_provider_payload(payload)

    assert payload["evidence"][0]["artifact_reference"] == "local-only.txt"
    assert "artifact_reference" not in compact["evidence"][0]

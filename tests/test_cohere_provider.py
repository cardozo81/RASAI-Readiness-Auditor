from __future__ import annotations

import json

import pytest

from rasai.ai_orchestration_unification import _structured_payload
from rasai.improvement_intelligence import _provider_payload
from rasai.provider_extensions import CohereProvider, build_semantic_provider
from rasai.provider_wire_schema import cohere_wire_schema, project_provider_request_body
from rasai.semantic import SemanticEvidenceInput, SemanticInput


def _input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-COHERE-1",
        page_url="https://example.com/cohere",
        title="Cohere",
        main_content="Persisted evidence only.",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EVD-1",
                evidence_type="TEXT_EXCERPT",
                source="test",
                observed_value={"text": "Persisted evidence only."},
            ),
        ),
    )


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "minLength": 1, "maxLength": 100},
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "uniqueItems": True,
                "items": {"type": "string", "enum": ["a", "b"]},
            },
            "choice": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"},
                ]
            },
        },
        "required": ["answer", "items", "choice"],
    }


def test_cohere_wire_schema_preserves_structure_and_drops_unsupported_constraints() -> None:
    projected = cohere_wire_schema(_schema())
    assert projected["type"] == "object"
    assert projected["additionalProperties"] is False
    assert projected["required"] == ["answer", "items", "choice"]
    assert "minLength" not in projected["properties"]["answer"]
    assert "maxLength" not in projected["properties"]["answer"]
    assert "minItems" not in projected["properties"]["items"]
    assert "maxItems" not in projected["properties"]["items"]
    assert "uniqueItems" not in projected["properties"]["items"]
    assert projected["properties"]["items"]["items"]["enum"] == ["a", "b"]
    assert "anyOf" in projected["properties"]["choice"]


def test_cohere_body_projection_changes_only_response_schema() -> None:
    payload = {
        "model": "command-a-03-2025",
        "messages": [{"role": "user", "content": "evidence"}],
        "metadata": {"schema": {"minItems": "must-not-change"}},
        "response_format": {"type": "json_object", "schema": _schema()},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    projected = json.loads(project_provider_request_body("COHERE", body).decode())
    assert projected["messages"] == payload["messages"]
    assert projected["metadata"] == payload["metadata"]
    assert "minItems" not in projected["response_format"]["schema"]["properties"]["items"]


def test_cohere_semantic_payload_is_evidence_bound_and_has_no_tools_or_documents() -> None:
    provider = CohereProvider(model="command-a-03-2025", api_key="test-key")
    payload = provider._request_payload(_input())
    assert payload["model"] == "command-a-03-2025"
    assert payload["response_format"]["type"] == "json_object"
    assert "schema" in payload["response_format"]
    assert "tools" not in payload
    assert "documents" not in payload
    assert "EVD-1" in json.dumps(payload, ensure_ascii=False)


def test_cohere_usage_prefers_billed_units_over_raw_tokens() -> None:
    provider = CohereProvider(model="command-a-03-2025", api_key="test-key")
    usage = provider._usage(
        {
            "usage": {
                "billed_units": {"input_tokens": 5, "output_tokens": 7},
                "tokens": {"input_tokens": 50, "output_tokens": 70},
            }
        }
    )
    assert usage is not None
    assert usage.input_tokens == 5
    assert usage.output_tokens == 7
    assert usage.total_tokens == 12
    assert usage.cached_input_tokens is None
    assert usage.reasoning_tokens is None


def test_cohere_extracts_chat_v2_text_content() -> None:
    provider = CohereProvider(model="command-a-03-2025", api_key="test-key")
    assert provider._extract_payload(
        {"message": {"content": [{"type": "text", "text": '{"answer":"ok"}'}]}}
    ) == {"answer": "ok"}


def test_cohere_shared_specialist_consumers_use_same_structured_contract() -> None:
    provider = CohereProvider(model="command-a-03-2025", api_key="test-key")
    specialist = _structured_payload(
        provider,
        schema_name="rasai_test",
        instructions="Return JSON only.",
        user_text="Persisted evidence.",
        schema=_schema(),
    )
    improvement = _provider_payload(
        provider,
        instructions="Return JSON only.",
        user_text="Persisted evidence.",
        schema=_schema(),
    )
    for payload in (specialist, improvement):
        assert payload["model"] == "command-a-03-2025"
        assert payload["response_format"]["type"] == "json_object"
        assert "minItems" not in payload["response_format"]["schema"]["properties"]["items"]
        assert "tools" not in payload
        assert "documents" not in payload


def test_cohere_factory_uses_public_default_and_is_explicit_selection() -> None:
    provider = build_semantic_provider("cohere", env={"COHERE_API_KEY": "test-key"})
    assert provider.name == "COHERE"
    assert provider.model == "command-a-03-2025"
    assert provider.api_key == "test-key"
    assert provider.reasoning_profile == "PROVIDER_DEFAULT"
    assert provider.pricing_runtime_conditions() == {
        "commercial_mode": "UNKNOWN",
        "operation_mode": "REALTIME",
        "region": "GLOBAL",
    }


def test_cohere_commercial_mode_is_explicit_and_validated() -> None:
    trial = build_semantic_provider(
        "cohere",
        env={
            "COHERE_API_KEY": "test-key",
            "RASAI_COHERE_COMMERCIAL_MODE": "trial",
        },
    )
    production = build_semantic_provider(
        "cohere",
        env={
            "COHERE_API_KEY": "test-key",
            "RASAI_COHERE_COMMERCIAL_MODE": "PRODUCTION",
        },
    )
    assert trial.pricing_runtime_conditions()["commercial_mode"] == "TRIAL"
    assert production.pricing_runtime_conditions()["commercial_mode"] == "PRODUCTION"

    with pytest.raises(ValueError, match="RASAI_COHERE_COMMERCIAL_MODE"):
        build_semantic_provider(
            "cohere",
            env={
                "COHERE_API_KEY": "test-key",
                "RASAI_COHERE_COMMERCIAL_MODE": "guessed",
            },
        )

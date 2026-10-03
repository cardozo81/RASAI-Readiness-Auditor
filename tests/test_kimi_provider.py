from __future__ import annotations

from datetime import datetime, timezone
import json

from rasai.ai_catalog_control_plane import _ADAPTER_TYPES
from rasai.ai_cost_policy import resolve_observed_cost
from rasai.ai_orchestration_unification import _structured_payload
from rasai.improvement_intelligence import _provider_payload
from rasai.provider_extensions import KimiProvider, build_semantic_provider
from rasai.provider_registry import get_provider_registration
from rasai.provider_wire_schema import kimi_wire_schema, project_provider_request_body
from rasai.semantic import ProviderState, SemanticEvidenceInput, SemanticInput


def _input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-KIMI-1",
        page_url="https://example.com/kimi",
        title="Kimi",
        main_content="Persisted evidence only.",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(SemanticEvidenceInput(
            evidence_id="EVD-1",
            evidence_type="TEXT_EXCERPT",
            source="test",
            observed_value={"text": "Persisted evidence only."},
        ),),
    )


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "minLength": 1, "maxLength": 100},
            "items": {
                "type": "array", "minItems": 1, "maxItems": 2, "uniqueItems": True,
                "items": {"type": "string", "enum": ["a", "b"]},
            },
        },
        "required": ["answer", "items"],
    }


def test_kimi_wire_schema_keeps_structure_and_localizes_value_constraints() -> None:
    projected = kimi_wire_schema(_schema())
    assert projected["type"] == "object"
    assert projected["additionalProperties"] is False
    assert projected["required"] == ["answer", "items"]
    assert "minLength" not in projected["properties"]["answer"]
    assert "maxLength" not in projected["properties"]["answer"]
    assert "minItems" not in projected["properties"]["items"]
    assert "maxItems" not in projected["properties"]["items"]
    assert "uniqueItems" not in projected["properties"]["items"]
    assert projected["properties"]["items"]["items"]["enum"] == ["a", "b"]


def test_kimi_body_projection_changes_only_structured_output_schema() -> None:
    payload = {
        "model": "kimi-k3",
        "messages": [{"role": "user", "content": "evidence"}],
        "metadata": {"schema": {"minItems": "must-not-change"}},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "test", "schema": _schema(), "strict": True},
        },
    }
    projected = json.loads(project_provider_request_body("KIMI", json.dumps(payload).encode()).decode())
    assert projected["messages"] == payload["messages"]
    assert projected["metadata"] == payload["metadata"]
    assert "minItems" not in projected["response_format"]["json_schema"]["schema"]["properties"]["items"]


def test_kimi_semantic_payload_is_evidence_bound_strict_and_low_by_default() -> None:
    provider = KimiProvider(model="kimi-k3", api_key="test-key")
    payload = provider._request_payload(_input())
    assert payload["model"] == "kimi-k3"
    assert payload["reasoning_effort"] == "low"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    for forbidden in ("tools", "tool_choice", "documents", "prompt_cache_options"):
        assert forbidden not in payload
    assert "EVD-1" in json.dumps(payload, ensure_ascii=False)


def test_kimi_usage_keeps_cache_write_inside_total_prompt_tokens() -> None:
    provider = KimiProvider(model="kimi-k3", api_key="test-key")
    usage = provider._usage({"usage": {
        "prompt_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 20},
        "completion_tokens": 40,
        "total_tokens": 160,
    }})
    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.cached_input_tokens == 30
    assert usage.output_tokens == 40
    assert usage.reasoning_tokens is None
    assert usage.total_tokens == 160


def test_kimi_extracts_final_content_not_reasoning_content() -> None:
    provider = KimiProvider(model="kimi-k3", api_key="test-key")
    payload = provider._extract_payload({
        "choices": [{"message": {"reasoning_content": "private", "content": '{"answer":"ok"}'}}]
    })
    assert payload == {"answer": "ok"}


def test_kimi_shared_consumers_keep_strict_schema_low_reasoning_and_no_tools() -> None:
    provider = KimiProvider(model="kimi-k3", api_key="test-key")
    specialist = _structured_payload(
        provider, schema_name="rasai_test", instructions="Return JSON only.",
        user_text="Persisted evidence.", schema=_schema(),
    )
    improvement = _provider_payload(
        provider, instructions="Return JSON only.", user_text="Persisted evidence.", schema=_schema(),
    )
    for payload in (specialist, improvement):
        assert payload["model"] == "kimi-k3"
        assert payload["reasoning_effort"] == "low"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert "minItems" not in payload["response_format"]["json_schema"]["schema"]["properties"]["items"]
        assert "tools" not in payload
        assert "prompt_cache_options" not in payload


def test_kimi_factory_registry_and_pricing_are_explicit_and_traceable() -> None:
    provider = build_semantic_provider("kimi", env={"MOONSHOT_API_KEY": "test-key"})
    alias = build_semantic_provider("moonshot", env={"MOONSHOT_API_KEY": "test-key"})
    assert provider.name == alias.name == "KIMI"
    assert provider.model == alias.model == "kimi-k3"
    assert provider.endpoint == "https://api.moonshot.ai/v1/chat/completions"
    assert provider.reasoning_profile == "LOW"
    assert provider.pricing_runtime_conditions() == {
        "cache_ttl": "5M", "operation_mode": "REALTIME", "region": "INTERNATIONAL",
    }
    registration = get_provider_registration("kimi")
    assert registration is not None and registration.explicit_only and not registration.auto_eligible
    assert _ADAPTER_TYPES["KIMI"] == "KIMI_CHAT_COMPLETIONS"
    usage = provider._usage({"usage": {
        "prompt_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 20},
        "completion_tokens": 40,
        "total_tokens": 160,
    }})
    priced = resolve_observed_cost(
        "KIMI", "kimi-k3", usage,
        datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc),
        runtime_conditions=provider.pricing_runtime_conditions(),
    )
    assert priced.estimated_cost == 0.000879
    assert priced.currency == "USD"
    assert priced.pricing_rule_id == "kimi-k3-international-realtime-5m"


def test_kimi_partial_semantic_output_fails_closed() -> None:
    provider = KimiProvider(
        model="kimi-k3", api_key="test-key",
        transport=lambda *_: {
            "choices": [{"message": {"content": '{"assessments":[]}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )
    result = provider.analyze(_input())
    assert result.state is ProviderState.UNAVAILABLE
    assert result.response is None

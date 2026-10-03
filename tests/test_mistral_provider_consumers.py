from __future__ import annotations

from rasai.ai_catalog_control_plane import _ADAPTER_TYPES
from rasai.ai_orchestration_unification import _structured_payload
from rasai.improvement_intelligence import _provider_payload
from rasai.provider_extensions import MistralProvider
from rasai.provider_registry import get_provider_registration


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def test_mistral_shared_consumers_keep_standard_structured_contract() -> None:
    provider = MistralProvider(model="mistral-small-2603", api_key="test-key")
    specialist = _structured_payload(
        provider,
        schema_name="rasai_test",
        instructions="Return the requested JSON.",
        user_text="Evidence-bound input.",
        schema=_schema(),
    )
    improvement = _provider_payload(
        provider,
        instructions="Return the requested JSON.",
        user_text="Evidence-bound input.",
        schema=_schema(),
    )

    for payload in (specialist, improvement):
        assert payload["model"] == "mistral-small-2603"
        assert payload["service_tier"] == "standard_only"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["schema"] == _schema()


def test_mistral_control_plane_identity_matches_auto_registry() -> None:
    registration = get_provider_registration("mistral")
    assert registration is not None
    assert registration.provider_name == "MISTRAL"
    assert registration.explicit_only is False
    assert registration.auto_eligible is True
    assert _ADAPTER_TYPES["MISTRAL"] == "MISTRAL_CHAT_COMPLETIONS"

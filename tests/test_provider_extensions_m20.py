from __future__ import annotations

import json
import unittest

from rasai.m18_ai import ProviderState, RuntimeProviderState
from rasai.m20_ai import ContentEvidenceInput, ContentFindingInput, ContentRemediationRequest
from rasai.provider_extensions import AnthropicProvider, GeminiProvider, QwenProvider, XAIProvider
from rasai.provider_extensions_m20 import build_content_remediation_router


def _request() -> ContentRemediationRequest:
    return ContentRemediationRequest(
        snapshot_id="SNP-M20-EXT",
        page_id="PAG-EXT",
        page_url="https://example.com/ext",
        device="MOBILE",
        title="Produto Alpha",
        main_content="Produto Alpha possui descrição observada.",
        findings=(
            ContentFindingInput(
                finding_id="FND-1",
                rule_id="BR-GEO-040",
                title="Contexto insuficiente",
                severity="MEDIUM",
                expected_condition="Explicar o produto com clareza.",
                observed_value={"summary": "Descrição curta"},
                evidence_ids=("EVD-1",),
            ),
        ),
        evidence=(
            ContentEvidenceInput(
                evidence_id="EVD-1",
                evidence_type="TEXT_EXCERPT",
                source="test",
                observed_value={"text": "Produto Alpha possui descrição observada."},
            ),
        ),
    )


def _suggestions() -> dict[str, object]:
    return {
        "suggestions": [{
            "finding_id": "FND-1",
            "objective": "Melhorar clareza",
            "target_location": "Descrição principal",
            "proposed_text": "Produto Alpha possui descrição observada.",
            "evidence_ids": ["EVD-1"],
            "confidence": 0.8,
            "review_note": "Revisar antes de publicar.",
        }]
    }


class ProviderExtensionM20Tests(unittest.TestCase):
    def _assert_success(self, provider, response, expected_fragment: str) -> None:
        calls: list[dict[str, object]] = []

        def transport(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
            return response

        provider._transport = transport
        router = build_content_remediation_router(provider)
        result = router.analyze(_request())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(result.provider, provider.name)
        self.assertEqual(len(result.suggestions), 1)
        self.assertIn(expected_fragment, json.dumps(calls[0]["body"]))
        attempts = router.consume_attempts()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].provider, provider.name)
        self.assertEqual(attempts[0].status.value, "SUCCESS")

    def test_xai_m20_uses_responses_schema(self) -> None:
        provider = XAIProvider(model="grok-4.6", api_key="x")
        self._assert_success(
            provider,
            {"output_text": json.dumps(_suggestions())},
            "rasai_content_remediation",
        )

    def test_qwen_m20_uses_chat_completions_schema(self) -> None:
        provider = QwenProvider(model="qwen3.8-max", api_key="x")
        self._assert_success(
            provider,
            {"choices": [{"message": {"content": json.dumps(_suggestions())}}]},
            "response_format",
        )

    def test_gemini_m20_uses_interactions_schema(self) -> None:
        provider = GeminiProvider(model="gemini-3.8-flash", api_key="x")
        self._assert_success(
            provider,
            {"output_text": json.dumps(_suggestions())},
            "application/json",
        )

    def test_anthropic_m20_uses_messages_schema(self) -> None:
        provider = AnthropicProvider(model="claude-sonnet-5", api_key="x")
        self._assert_success(
            provider,
            {"content": [{"type": "text", "text": json.dumps(_suggestions())}]},
            "output_config",
        )

    def test_quarantined_m7_provider_is_not_reactivated_for_m20(self) -> None:
        provider = XAIProvider(model="grok-4.6", api_key="x")
        provider._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
        router = build_content_remediation_router(provider)
        result = router.analyze(_request())
        self.assertEqual(result.state, ProviderState.NOT_CONFIGURED)
        self.assertEqual(router.providers, ())


if __name__ == "__main__":
    unittest.main()

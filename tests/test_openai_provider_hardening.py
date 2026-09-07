from __future__ import annotations

import io
import json
from email.message import Message
import unittest
from urllib.error import HTTPError

from rasai.cli import _semantic_provider, build_parser
from rasai.m11 import _ai_usage_status
from rasai.openai_provider import (
    OpenAIProvider,
    SEMANTIC_RULE_CRITERIA,
    hardened_semantic_output_schema,
)
from rasai.semantic import (
    ProviderState,
    SEMANTIC_RULE_IDS,
    SemanticEvidenceInput,
    SemanticInput,
)


def _input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-1",
        page_url="https://example.com/produto",
        title="Produto Alpha",
        main_content="Conteúdo principal factual sobre Produto Alpha.",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EVD-1",
                evidence_type="TEXT_EXCERPT",
                source="test",
                observed_value={"text": "Produto Alpha"},
            ),
        ),
    )


def _assessment(rule_id: str) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "result": "UNKNOWN",
        "confidence": 0.0,
        "evidence_ids": [],
        "reasoning_summary": "Insufficient evidence in fixture.",
        "observed_value": {"summary": "", "details": []},
    }


def _provider_payload(rule_ids: tuple[str, ...] = SEMANTIC_RULE_IDS) -> dict[str, object]:
    return {
        "assessments": [_assessment(rule_id) for rule_id in rule_ids],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


class OpenAIProviderHardeningTests(unittest.TestCase):
    def test_rule_contract_covers_all_semantic_rules(self) -> None:
        self.assertEqual(tuple(SEMANTIC_RULE_CRITERIA), SEMANTIC_RULE_IDS)
        self.assertEqual(len(SEMANTIC_RULE_CRITERIA), 22)

        schema = hardened_semantic_output_schema()
        assessments = schema["properties"]["assessments"]
        self.assertEqual(assessments["minItems"], 22)
        self.assertEqual(assessments["maxItems"], 22)

    def test_prompt_explains_every_rule_and_requires_complete_set(self) -> None:
        provider = OpenAIProvider(model="gpt-test", api_key="test-key", transport=lambda *_: {})
        request = provider._request_payload(_input())
        instructions = request["instructions"]
        self.assertIn("exactly one item for every rule", instructions)
        for rule_id in SEMANTIC_RULE_IDS:
            self.assertIn(rule_id, instructions)
            self.assertIn(SEMANTIC_RULE_CRITERIA[rule_id], instructions)

    def test_complete_response_is_available(self) -> None:
        def transport(*_args):
            return {"output_text": json.dumps(_provider_payload())}

        result = OpenAIProvider(
            model="gpt-test",
            api_key="test-key",
            transport=transport,
        ).analyze(_input())

        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertIsNotNone(result.response)
        self.assertEqual(len(result.response.assessments), 22)

    def test_partial_response_is_not_published_as_available(self) -> None:
        def transport(*_args):
            return {"output_text": json.dumps(_provider_payload(SEMANTIC_RULE_IDS[:-1]))}

        result = OpenAIProvider(
            model="gpt-test",
            api_key="test-key",
            transport=transport,
        ).analyze(_input())

        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(result.reason, "AI_PROVIDER_UNAVAILABLE:INCOMPLETE_SEMANTIC_OUTPUT")
        self.assertIsNone(result.response)

    def test_http_429_retains_sanitized_quota_diagnostic(self) -> None:
        headers = Message()
        headers["x-request-id"] = "req_test-123"
        body = io.BytesIO(json.dumps({
            "error": {
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
                "message": "sensitive verbose message that must not be persisted",
            }
        }).encode("utf-8"))

        def transport(*_args):
            raise HTTPError(
                "https://api.openai.com/v1/responses",
                429,
                "Too Many Requests",
                headers,
                body,
            )

        result = OpenAIProvider(
            model="gpt-5.6-terra",
            api_key="test-key",
            transport=transport,
        ).analyze(_input())

        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(
            result.reason,
            "AI_PROVIDER_UNAVAILABLE:HTTP_429:type=insufficient_quota:code=credit_balance_exhausted:request_id=req_test-123",
        )
        self.assertNotIn("sensitive verbose message", result.reason)
        self.assertNotIn("test-key", result.reason)

    def test_cli_uses_hardened_provider(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "audit", "https://example.com", "--ai-provider", "openai", "--ai-model", "gpt-5.6-terra",
        ])
        provider = _semantic_provider(args)
        self.assertIsInstance(provider, OpenAIProvider)

    def test_report_ai_usage_distinguishes_failure_from_success(self) -> None:
        self.assertEqual(
            _ai_usage_status([{"provider": "DETERMINISTIC"}, {"provider": "UNAVAILABLE"}]),
            "TENTATIVA SEM SUCESSO",
        )
        self.assertEqual(
            _ai_usage_status([{"provider": "DETERMINISTIC"}, {"provider": "OPENAI"}]),
            "SIM",
        )
        self.assertEqual(_ai_usage_status([{"provider": "DETERMINISTIC"}]), "NÃO")


if __name__ == "__main__":
    unittest.main()

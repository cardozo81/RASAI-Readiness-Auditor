from __future__ import annotations

import json
import unittest

from rasai.m18_ai import ProviderState, ProviderUsage
from rasai.provider_extensions import (
    AnthropicProvider,
    GeminiProvider,
    QwenProvider,
    XAIProvider,
    build_semantic_provider,
)
from rasai.semantic import SEMANTIC_RULE_IDS, SemanticEvidenceInput, SemanticInput


def _input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-EXT-1",
        page_url="https://example.com/provider-extension",
        title="Provider extension",
        main_content="Evidence-bound provider extension fixture.",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EVD-1",
                evidence_type="TEXT_EXCERPT",
                source="test",
                observed_value={"text": "Provider extension"},
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


def _payload(rule_ids: tuple[str, ...] = SEMANTIC_RULE_IDS) -> dict[str, object]:
    return {
        "assessments": [_assessment(rule_id) for rule_id in rule_ids],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


class ProviderExtensionTests(unittest.TestCase):
    def test_legacy_auto_is_delegated_and_ignores_extension_keys(self) -> None:
        env = {
            "OPENAI_API_KEY": "openai",
            "DEEPSEEK_API_KEY": "deepseek",
            "MIMO_API_KEY": "mimo",
            "XAI_API_KEY": "xai",
            "DASHSCOPE_API_KEY": "qwen",
            "GEMINI_API_KEY": "gemini",
            "ANTHROPIC_API_KEY": "anthropic",
        }
        auto = build_semantic_provider("auto", env=env)
        self.assertEqual([provider.name for provider in auto.providers], ["OPENAI", "DEEPSEEK", "MIMO"])

    def test_legacy_explicit_provider_defaults_are_unchanged(self) -> None:
        openai = build_semantic_provider("openai", env={"OPENAI_API_KEY": "x"})
        deepseek = build_semantic_provider("deepseek", env={"DEEPSEEK_API_KEY": "x"})
        mimo = build_semantic_provider("mimo", env={"MIMO_API_KEY": "x"})
        self.assertEqual((openai.name, openai.model), ("OPENAI", "gpt-5.6-terra"))
        self.assertEqual((deepseek.name, deepseek.model), ("DEEPSEEK", "deepseek-v4-pro"))
        self.assertEqual((mimo.name, mimo.model), ("MIMO", "mimo-v2.5-pro"))

    def test_extension_defaults_aliases_and_provisional_status(self) -> None:
        cases = (
            ("xai", {"XAI_API_KEY": "x"}, "XAI", "grok-4.6"),
            ("grok", {"XAI_API_KEY": "x"}, "XAI", "grok-4.6"),
            ("qwen", {"DASHSCOPE_API_KEY": "x"}, "QWEN", "qwen3.8-max"),
            ("gemini", {"GEMINI_API_KEY": "x"}, "GEMINI", "gemini-3.8-flash"),
            ("anthropic", {"ANTHROPIC_API_KEY": "x"}, "ANTHROPIC", "claude-sonnet-5"),
            ("claude", {"ANTHROPIC_API_KEY": "x"}, "ANTHROPIC", "claude-sonnet-5"),
        )
        for selection, env, expected_name, expected_model in cases:
            with self.subTest(selection=selection):
                provider = build_semantic_provider(selection, env=env)
                self.assertEqual((provider.name, provider.model), (expected_name, expected_model))
                self.assertEqual(provider.policy.qualification, "PROVISIONAL")
                self.assertGreaterEqual(provider.policy.rank, 100)

    def test_extension_endpoint_override_is_explicit_and_isolated(self) -> None:
        provider = build_semantic_provider(
            "qwen",
            env={
                "DASHSCOPE_API_KEY": "x",
                "RASAI_QWEN_ENDPOINT": "https://workspace.example/v1/chat/completions",
            },
        )
        self.assertEqual(provider.endpoint, "https://workspace.example/v1/chat/completions")

    def test_xai_responses_contract_and_usage(self) -> None:
        calls: list[dict[str, object]] = []

        def transport(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
            return {
                "output_text": json.dumps(_payload()),
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens": 50,
                    "output_tokens_details": {"reasoning_tokens": 10},
                    "total_tokens": 150,
                },
            }

        provider = XAIProvider(model="grok-4.6", api_key="x", transport=transport)
        result = provider.analyze(_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(result.usage, ProviderUsage(100, 20, 50, 10, 150))
        request = calls[0]["body"]
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(request["reasoning"]["effort"], "high")
        self.assertEqual(calls[0]["url"], "https://api.x.ai/v1/responses")

    def test_qwen_chat_completions_contract(self) -> None:
        calls: list[dict[str, object]] = []

        def transport(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
            return {
                "choices": [{"message": {"content": json.dumps(_payload())}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            }

        provider = QwenProvider(model="qwen3.8-max", api_key="x", transport=transport)
        result = provider.analyze(_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(result.usage.input_tokens, 80)
        self.assertEqual(result.usage.output_tokens, 40)
        response_format = calls[0]["body"]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertIn("/chat/completions", calls[0]["url"])

    def test_gemini_interactions_contract_and_new_schema_response(self) -> None:
        calls: list[dict[str, object]] = []

        def transport(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
            return {
                "steps": [{
                    "type": "model_output",
                    "content": [{"type": "text", "text": json.dumps(_payload())}],
                }],
                "usage": {"prompt_tokens": 90, "completion_tokens": 45, "total_tokens": 135},
            }

        provider = GeminiProvider(model="gemini-3.8-flash", api_key="x", transport=transport)
        result = provider.analyze(_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(result.usage.input_tokens, 90)
        self.assertEqual(result.usage.output_tokens, 45)
        request = calls[0]["body"]
        self.assertEqual(request["response_format"]["mime_type"], "application/json")
        self.assertEqual(request["response_format"]["type"], "text")
        self.assertIn("x-goog-api-key", calls[0]["headers"])

    def test_anthropic_messages_contract_usage_and_refusal(self) -> None:
        calls: list[dict[str, object]] = []

        def success(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
            return {
                "content": [{"type": "text", "text": json.dumps(_payload())}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 70,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 10,
                    "output_tokens": 30,
                },
            }

        provider = AnthropicProvider(model="claude-sonnet-5", api_key="x", transport=success)
        result = provider.analyze(_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(result.usage, ProviderUsage(85, 10, 30, None, 115))
        request = calls[0]["body"]
        self.assertEqual(request["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(calls[0]["headers"]["anthropic-version"], "2023-06-01")

        refusal = AnthropicProvider(
            model="claude-sonnet-5",
            api_key="x",
            transport=lambda *_: {"stop_reason": "refusal", "content": []},
        )
        failed = refusal.analyze(_input())
        self.assertEqual(failed.state, ProviderState.UNAVAILABLE)
        self.assertEqual(failed.diagnostic.error_code, "REFUSAL")

    def test_missing_key_is_not_configured_and_never_calls_transport(self) -> None:
        called = False

        def transport(*_):
            nonlocal called
            called = True
            return {}

        provider = XAIProvider(model="grok-4.6", api_key=None, transport=transport)
        result = provider.analyze(_input())
        self.assertEqual(result.state, ProviderState.NOT_CONFIGURED)
        self.assertFalse(called)

    def test_partial_output_is_fail_closed_and_quarantined(self) -> None:
        provider = GeminiProvider(
            model="gemini-3.8-flash",
            api_key="x",
            transport=lambda *_: {"output_text": json.dumps(_payload(SEMANTIC_RULE_IDS[:-1]))},
        )
        first = provider.analyze(_input())
        second = provider.analyze(_input())
        self.assertEqual(first.state, ProviderState.UNAVAILABLE)
        self.assertEqual(first.diagnostic.error_class.value, "CONTRACT_ERROR")
        self.assertEqual(second.reason, "AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from rasai.console_config import State
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    DEFAULT_AI_TIMEOUT_SECONDS,
    DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    LOWEST_REASONING,
    SIMPLE_DEFAULT_MODELS,
    build_semantic_provider,
    environment_with_public_defaults,
)


class ProviderRuntimePolicyTests(unittest.TestCase):
    def test_public_defaults_use_simplest_models(self) -> None:
        self.assertEqual(SIMPLE_DEFAULT_MODELS["OPENAI"], "gpt-5.6-luna")
        self.assertEqual(SIMPLE_DEFAULT_MODELS["DEEPSEEK"], "deepseek-v4-flash")
        self.assertEqual(SIMPLE_DEFAULT_MODELS["MIMO"], "mimo-v2.6-flash")
        self.assertEqual(SIMPLE_DEFAULT_MODELS["QWEN"], "qwen3.8-flash")
        self.assertEqual(SIMPLE_DEFAULT_MODELS["MISTRAL"], "mistral-small-2603")

    def test_public_defaults_use_lowest_supported_effort(self) -> None:
        self.assertEqual(LOWEST_REASONING["OPENAI"], "NONE")
        self.assertEqual(LOWEST_REASONING["DEEPSEEK"], "NONE")
        self.assertEqual(LOWEST_REASONING["MIMO"], "NONE")
        self.assertEqual(LOWEST_REASONING["XAI"], "LOW")
        self.assertEqual(LOWEST_REASONING["GEMINI"], "LOW")
        self.assertEqual(LOWEST_REASONING["ANTHROPIC"], "LOW")
        self.assertEqual(LOWEST_REASONING["QWEN"], "NONE")
        self.assertEqual(LOWEST_REASONING["MISTRAL"], "PROVIDER_DEFAULT")

    def test_explicit_environment_override_is_preserved(self) -> None:
        env = environment_with_public_defaults({
            "RASAI_OPENAI_MODEL": "gpt-5.6-sol",
            "RASAI_OPENAI_REASONING_EFFORT": "HIGH",
        })
        self.assertEqual(env["RASAI_OPENAI_MODEL"], "gpt-5.6-sol")
        self.assertEqual(env["RASAI_OPENAI_REASONING_EFFORT"], "HIGH")

    def test_direct_runtime_builder_applies_public_ai_timeout_default(self) -> None:
        provider = build_semantic_provider(
            "openai",
            env={"OPENAI_API_KEY": "test-key"},
        )
        self.assertEqual(DEFAULT_AI_TIMEOUT_SECONDS, 180.0)
        self.assertEqual(provider.timeout, 180.0)

    def test_direct_runtime_builder_applies_timeout_override_to_explicit_provider(self) -> None:
        provider = build_semantic_provider(
            "openai",
            env={
                "OPENAI_API_KEY": "test-key",
                AI_TIMEOUT_ENV: "240",
            },
        )
        self.assertEqual(provider.timeout, 240.0)

    def test_direct_runtime_builder_applies_timeout_override_to_auto_candidates(self) -> None:
        router = build_semantic_provider(
            "auto",
            env={
                "OPENAI_API_KEY": "openai-key",
                "DEEPSEEK_API_KEY": "deepseek-key",
                "GEMINI_API_KEY": "gemini-key",
                "MISTRAL_API_KEY": "mistral-key",
                AI_TIMEOUT_ENV: "210",
            },
        )
        self.assertGreaterEqual(len(router.providers), 2)
        self.assertTrue(all(item.timeout == 210.0 for item in router.providers))
        self.assertNotIn("MISTRAL", {item.name for item in router.providers})

    def test_direct_runtime_builder_rejects_invalid_ai_timeout_only_when_ai_enabled(self) -> None:
        for raw in ("0", "-1", "nan", "inf", "invalid"):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, AI_TIMEOUT_ENV):
                    build_semantic_provider(
                        "openai",
                        env={"OPENAI_API_KEY": "test-key", AI_TIMEOUT_ENV: raw},
                    )
                none_provider = build_semantic_provider(
                    "none",
                    env={AI_TIMEOUT_ENV: raw},
                )
                self.assertEqual(none_provider.name, "NONE")

    def test_ai_none_ignores_configured_mistral(self) -> None:
        provider = build_semantic_provider(
            "none",
            env={
                "MISTRAL_API_KEY": "test-key",
                "RASAI_MISTRAL_MODEL": "mistral-small-2603",
            },
        )
        self.assertEqual(provider.name, "NONE")

    def test_console_web_timeout_default_is_120_seconds(self) -> None:
        self.assertEqual(DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS, 120.0)
        self.assertEqual(State().web_timeout, 120.0)

    def test_mistral_explicit_builder_uses_fixed_global_endpoint(self) -> None:
        provider = build_semantic_provider("mistral", env={"MISTRAL_API_KEY": "x"})
        self.assertEqual(provider.name, "MISTRAL")
        self.assertEqual(provider.model, "mistral-small-2603")
        self.assertEqual(provider.endpoint, "https://api.mistral.ai/v1/chat/completions")
        self.assertEqual(provider.reasoning_profile, "PROVIDER_DEFAULT")

    def test_qwen_default_reasoning_is_none_and_override_is_supported(self) -> None:
        qwen = build_semantic_provider(
            "qwen",
            env={"DASHSCOPE_API_KEY": "x", "RASAI_QWEN_MODEL": "qwen3.8-flash"},
        )
        self.assertEqual(qwen.reasoning_profile, "NONE")
        payload = qwen._request_payload(type("Req", (), {
            "allowed_evidence_ids": frozenset(),
            "provider_payload": lambda self: {},
            "primary_language": "pt-BR",
            "market": "BR",
        })())
        self.assertEqual(payload["reasoning_effort"], "none")

        qwen_high = build_semantic_provider(
            "qwen",
            env={
                "DASHSCOPE_API_KEY": "x",
                "RASAI_QWEN_MODEL": "qwen3.8-flash",
                "RASAI_QWEN_REASONING_EFFORT": "HIGH",
            },
        )
        self.assertEqual(qwen_high.reasoning_profile, "HIGH")
        payload_high = qwen_high._request_payload(type("Req", (), {
            "allowed_evidence_ids": frozenset(),
            "provider_payload": lambda self: {},
            "primary_language": "pt-BR",
            "market": "BR",
        })())
        self.assertEqual(payload_high["reasoning_effort"], "high")

    def test_xai_and_gemini_payloads_are_lowered(self) -> None:
        xai = build_semantic_provider("xai", env={"XAI_API_KEY": "x", "RASAI_XAI_MODEL": "grok-4.6"})
        self.assertEqual(xai.reasoning_profile, "LOW")
        gemini = build_semantic_provider("gemini", env={"GEMINI_API_KEY": "x", "RASAI_GEMINI_MODEL": "gemini-3.8-flash"})
        self.assertEqual(gemini.reasoning_profile, "LOW")


if __name__ == "__main__":
    unittest.main()

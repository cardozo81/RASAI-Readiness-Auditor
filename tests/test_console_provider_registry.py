from __future__ import annotations

import unittest

from rasai.console_config import (
    ENV_NAMES,
    PROVIDER_MENU_CHOICES,
    State,
    build_command,
    provider_capabilities,
    validate_env_value,
)
from rasai.console_cost import estimate_exposure
from rasai.provider_registry import auto_provider_ids, provider_registrations


class ConsoleProviderRegistryTests(unittest.TestCase):
    def test_console_menu_is_derived_from_canonical_registry(self) -> None:
        expected = (
            "none",
            *(item.id for item in provider_registrations()),
            "auto",
        )
        self.assertEqual(PROVIDER_MENU_CHOICES, expected)
        self.assertEqual(
            PROVIDER_MENU_CHOICES,
            (
                "none",
                "openai",
                "deepseek",
                "mimo",
                "xai",
                "qwen",
                "gemini",
                "anthropic",
                "auto",
            ),
        )

    def test_extension_environment_variables_are_exposed_without_duplicates(self) -> None:
        self.assertEqual(len(ENV_NAMES), len(set(ENV_NAMES)))
        for name in (
            "XAI_API_KEY",
            "DASHSCOPE_API_KEY",
            "GEMINI_API_KEY",
            "ANTHROPIC_API_KEY",
            "RASAI_XAI_MODEL",
            "RASAI_QWEN_MODEL",
            "RASAI_GEMINI_MODEL",
            "RASAI_ANTHROPIC_MODEL",
            "RASAI_XAI_ENDPOINT",
            "RASAI_QWEN_ENDPOINT",
            "RASAI_GEMINI_ENDPOINT",
            "RASAI_ANTHROPIC_ENDPOINT",
            "RASAI_AI_EXCHANGE_LOG_MAX_BYTES",
        ):
            self.assertIn(name, ENV_NAMES)

    def test_extensions_are_fail_closed_without_credentials(self) -> None:
        capabilities = provider_capabilities({})
        for provider_id in ("xai", "qwen", "gemini", "anthropic"):
            with self.subTest(provider=provider_id):
                self.assertFalse(capabilities[provider_id].available)
                self.assertIn("não configurada", capabilities[provider_id].reason)
                self.assertIn("PROVISIONAL", capabilities[provider_id].reason)
                self.assertNotIn("explicit-only", capabilities[provider_id].reason)

    def test_extensions_become_auto_eligible_with_credentials(self) -> None:
        environment = {
            "XAI_API_KEY": "x",
            "DASHSCOPE_API_KEY": "x",
            "GEMINI_API_KEY": "x",
            "ANTHROPIC_API_KEY": "x",
        }
        capabilities = provider_capabilities(environment)
        for provider_id in ("xai", "qwen", "gemini", "anthropic"):
            with self.subTest(provider=provider_id):
                self.assertTrue(capabilities[provider_id].available)
                self.assertIn("PROVISIONAL", capabilities[provider_id].reason)
                self.assertNotIn("explicit-only", capabilities[provider_id].reason)
        self.assertTrue(capabilities["auto"].available)

    def test_auto_pool_includes_every_registry_provider_marked_eligible(self) -> None:
        self.assertEqual(
            auto_provider_ids(),
            ("openai", "deepseek", "mimo", "xai", "qwen", "gemini", "anthropic"),
        )
        extension_only = {
            "XAI_API_KEY": "x",
            "DASHSCOPE_API_KEY": "x",
            "GEMINI_API_KEY": "x",
            "ANTHROPIC_API_KEY": "x",
        }
        self.assertTrue(provider_capabilities(extension_only)["auto"].available)

    def test_auto_exposure_counts_every_configured_eligible_provider(self) -> None:
        import os
        previous = {
            key: os.environ.get(key)
            for key in (
                "OPENAI_API_KEY",
                "DEEPSEEK_API_KEY",
                "MIMO_API_KEY",
                "XAI_API_KEY",
                "DASHSCOPE_API_KEY",
                "GEMINI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
        }
        try:
            for key in previous:
                os.environ.pop(key, None)
            os.environ["OPENAI_API_KEY"] = "sk-test"
            os.environ["XAI_API_KEY"] = "x"
            os.environ["DASHSCOPE_API_KEY"] = "x"
            os.environ["GEMINI_API_KEY"] = "x"
            os.environ["ANTHROPIC_API_KEY"] = "x"
            state = State(
                target="https://example.com",
                max_pages=2,
                ai_provider="auto",
            )
            estimate = estimate_exposure(state)
            self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 10))
            self.assertTrue(any("5 provider" in reason for reason in estimate.reasons))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_extension_build_command_uses_stable_extended_cli(self) -> None:
        state = State(
            target="https://example.com",
            ai_provider="gemini",
            ai_model="gemini-3.8-flash",
        )
        command = build_command(state)
        self.assertIn("--ai-provider", command)
        self.assertIn("gemini", command)
        self.assertIn("--ai-model", command)
        self.assertIn("gemini-3.8-flash", command)

    def test_registry_drives_model_and_key_validation(self) -> None:
        self.assertEqual(
            validate_env_value("RASAI_QWEN_MODEL", "qwen3.8-flash"),
            "qwen3.8-flash",
        )
        with self.assertRaises(ValueError):
            validate_env_value("RASAI_QWEN_MODEL", "unknown")
        with self.assertRaises(ValueError):
            validate_env_value("MIMO_API_KEY", "tp-test")
        self.assertEqual(validate_env_value("MIMO_API_KEY", "sk-test"), "sk-test")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from rasai.cli import _semantic_provider, build_parser


class M18TimeoutConfigurationTests(unittest.TestCase):
    def test_explicit_provider_uses_longer_cli_runtime_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "audit",
            "https://example.com",
            "--ai-provider",
            "openai",
        ])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            provider = _semantic_provider(args)
        self.assertEqual(provider.name, "OPENAI")
        self.assertEqual(provider.timeout, 180.0)

    def test_timeout_environment_override_applies_to_all_auto_candidates(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "audit",
            "https://example.com",
            "--ai-provider",
            "auto",
        ])
        environment = {
            "OPENAI_API_KEY": "openai-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "MIMO_API_KEY": "mimo-key",
            "RASAI_AI_TIMEOUT_SECONDS": "240",
        }
        with patch.dict(os.environ, environment, clear=True):
            router = _semantic_provider(args)
        self.assertEqual([item.name for item in router.providers], ["OPENAI", "DEEPSEEK", "MIMO"])
        self.assertTrue(all(item.timeout == 240.0 for item in router.providers))

    def test_invalid_timeout_environment_value_is_rejected_only_when_ai_is_enabled(self) -> None:
        parser = build_parser()
        enabled = parser.parse_args([
            "audit",
            "https://example.com",
            "--ai-provider",
            "openai",
        ])
        disabled = parser.parse_args([
            "audit",
            "https://example.com",
            "--ai-provider",
            "none",
        ])
        environment = {
            "OPENAI_API_KEY": "test-key",
            "RASAI_AI_TIMEOUT_SECONDS": "0",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "RASAI_AI_TIMEOUT_SECONDS"):
                _semantic_provider(enabled)
            provider = _semantic_provider(disabled)
        self.assertEqual(provider.name, "NONE")


if __name__ == "__main__":
    unittest.main()

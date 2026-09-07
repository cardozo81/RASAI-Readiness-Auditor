from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from rasai.cli import _semantic_provider, build_parser
from rasai.m18_reporting import enrich_remediation_html, enrich_report_html


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


class M18ReportLayoutTests(unittest.TestCase):
    @staticmethod
    def _session() -> dict[str, object]:
        return {
            "enabled": 1,
            "status": "DEGRADED",
            "strategy": "SINGLE_PROVIDER",
            "configured_chain": json.dumps([
                {
                    "provider": "OPENAI",
                    "model": "gpt-5.6-terra",
                    "reasoning_profile": "HIGH",
                }
            ]),
            "initial_provider": "OPENAI",
            "initial_model": "gpt-5.6-terra",
            "initial_reasoning_profile": "HIGH",
            "effective_provider": None,
            "effective_model": None,
            "effective_reasoning_profile": None,
        }

    def test_report_telemetry_is_inserted_inside_main_content(self) -> None:
        html = (
            "<!doctype html><html><head><title>Report</title></head><body>"
            "<aside class='m15-sidebar'></aside>"
            "<main class='page m15-main'><section>Conteúdo</section></main>"
            "</body></html>"
        )
        with patch("rasai.m18_reporting._load", return_value=(self._session(), [], 2)):
            enriched = enrich_report_html(html, audit_id="AUD-1", workspace=object())
        self.assertLess(enriched.index("id='ai-runtime'"), enriched.index("</main>"))
        self.assertLess(enriched.index(".m18-ai{"), enriched.index("</head>"))
        self.assertIn(".m18-table-wrap{display:block;width:100%;max-width:100%;overflow-x:auto", enriched)
        self.assertIn("min-width:1050px", enriched)
        self.assertIn("width:calc(100% - var(--m15-sidebar));max-width:1280px", enriched)
        self.assertIn("@media(max-width:820px){.page.m15-main{width:100%;max-width:100%}}", enriched)

    def test_remediation_context_is_inserted_inside_main_content(self) -> None:
        html = (
            "<!doctype html><html><head><title>Remediation</title></head><body>"
            "<main class='wrap'><section>Conteúdo</section></main>"
            "</body></html>"
        )
        with patch("rasai.m18_reporting._load", return_value=(self._session(), [], 2)):
            enriched = enrich_remediation_html(html, audit_id="AUD-1", workspace=object())
        self.assertLess(enriched.index("id='ai-remediation-context'"), enriched.index("</main>"))
        self.assertLess(enriched.index(".m18-ai{"), enriched.index("</head>"))


if __name__ == "__main__":
    unittest.main()

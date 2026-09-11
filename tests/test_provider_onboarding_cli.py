from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import patch

from rasai.provider_cli import main as provider_cli_main
from rasai.provider_onboarding import (
    find_provider_onboarding,
    provider_onboarding_integrity_issues,
    provider_onboarding_records,
)
from rasai.search_intelligence.config import SERP_ENV_NAMES, SERP_PROVIDER_KEY_ENVS
from rasai.search_intelligence.provider_catalog import (
    SERP_PROVIDER_REGISTRY,
    serp_provider_ids,
    serp_provider_key_envs,
)
from rasai.search_intelligence.runtime import live_provider_ids


class ProviderOnboardingTests(unittest.TestCase):
    def test_onboarding_contract_is_complete_and_runtime_aligned(self) -> None:
        self.assertEqual((), provider_onboarding_integrity_issues())
        self.assertEqual(serp_provider_ids(), live_provider_ids())
        self.assertEqual(serp_provider_key_envs(), SERP_PROVIDER_KEY_ENVS)
        for key_env in serp_provider_key_envs():
            self.assertIn(key_env, SERP_ENV_NAMES)
        self.assertEqual("provider-driven", SERP_PROVIDER_REGISTRY[1].pagination_mode)
        for registration in SERP_PROVIDER_REGISTRY:
            if registration.id != "serpapi-bing":
                self.assertEqual("fixed-10", registration.pagination_mode)

    def test_records_report_configuration_state_without_secret_value(self) -> None:
        environment = {
            "OPENAI_API_KEY": "sk-super-secret-openai",
            "RASAI_ZENSERP_API_KEY": "zen-super-secret",
        }
        records = provider_onboarding_records(environment)
        openai = next(item for item in records if item.kind == "ai" and item.id == "openai")
        zenserp = next(item for item in records if item.kind == "serp" and item.id == "zenserp")
        self.assertTrue(openai.configured)
        self.assertTrue(zenserp.configured)
        serialized = json.dumps([item.public_dict() for item in records])
        self.assertNotIn("sk-super-secret-openai", serialized)
        self.assertNotIn("zen-super-secret", serialized)

    def test_ai_alias_resolves_to_canonical_onboarding_record(self) -> None:
        records = find_provider_onboarding("github-copilot", {}, kind="ai")
        self.assertEqual(1, len(records))
        self.assertEqual("copilot", records[0].id)
        self.assertTrue(records[0].explicit_only)
        self.assertFalse(records[0].auto_eligible)


class ProviderCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str], environment: dict[str, str] | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, environment or {}, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = provider_cli_main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_json_output_never_contains_secret_values(self) -> None:
        code, output, error = self.run_cli(
            ["--json"],
            {
                "OPENAI_API_KEY": "sk-do-not-print",
                "RASAI_SCRAPINGDOG_API_KEY": "dog-do-not-print",
            },
        )
        self.assertEqual(0, code, error)
        self.assertNotIn("sk-do-not-print", output)
        self.assertNotIn("dog-do-not-print", output)
        payload = json.loads(output)
        openai = next(item for item in payload if item["kind"] == "ai" and item["id"] == "openai")
        scrapingdog = next(item for item in payload if item["kind"] == "serp" and item["id"] == "scrapingdog")
        self.assertTrue(openai["configured"])
        self.assertTrue(scrapingdog["configured"])
        self.assertIn("platform.openai.com", openai["credential_url"])
        self.assertTrue(scrapingdog["free_tier"])

    def test_provider_alias_filter_and_human_output(self) -> None:
        code, output, error = self.run_cli(["--provider", "github-copilot"])
        self.assertEqual(0, code, error)
        self.assertIn("[AI] copilot - GitHub Copilot", output)
        self.assertIn("COPILOT_GITHUB_TOKEN", output)
        self.assertIn("personal-access-tokens", output)
        self.assertIn("Explicit-only   : sim", output)

    def test_configured_only_filters_without_exposing_values(self) -> None:
        code, output, error = self.run_cli(
            ["--configured-only", "--json"],
            {
                "GEMINI_API_KEY": "gem-secret",
                "RASAI_ZENSERP_API_KEY": "zen-secret",
            },
        )
        self.assertEqual(0, code, error)
        payload = json.loads(output)
        self.assertEqual(
            {("ai", "gemini"), ("serp", "zenserp")},
            {(item["kind"], item["id"]) for item in payload},
        )
        self.assertNotIn("gem-secret", output)
        self.assertNotIn("zen-secret", output)

    def test_unknown_provider_fails_closed(self) -> None:
        code, output, error = self.run_cli(["--provider", "does-not-exist"])
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertIn("provider não encontrado", error)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from rasai import console_provider_environment as provider_environment
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.search_intelligence.config import (
    SCRAPINGDOG_KEY_ENV,
    SERP_PROVIDER_ENV,
    ZENSERP_KEY_ENV,
)
from rasai.search_intelligence.provider_catalog import serp_provider_ids


class ConsoleProviderEnvironmentTests(unittest.TestCase):
    def test_serp_provider_enum_is_derived_from_canonical_registry(self) -> None:
        spec = provider_environment.SPEC_BY_NAME[SERP_PROVIDER_ENV]
        self.assertEqual(serp_provider_ids(), spec.accepted)
        for provider_id in serp_provider_ids():
            self.assertEqual(provider_id, provider_environment._validate(SERP_PROVIDER_ENV, provider_id))
        with self.assertRaises(ValueError):
            provider_environment._validate(SERP_PROVIDER_ENV, "unknown-provider")

    def test_serp_credential_specs_have_provider_onboarding_urls(self) -> None:
        specs = {item.name: item for item in provider_environment.environment_specs()}
        zenserp = specs[ZENSERP_KEY_ENV]
        scrapingdog = specs[SCRAPINGDOG_KEY_ENV]
        self.assertTrue(zenserp.sensitive)
        self.assertTrue(scrapingdog.sensitive)
        self.assertIn("app.zenserp.com", zenserp.source)
        self.assertIn("api.scrapingdog.com", scrapingdog.source)
        self.assertIn("Search Intelligence", zenserp.category)
        self.assertIn("Search Intelligence", scrapingdog.category)

    def test_ai_credential_specs_are_enriched_from_provider_registry(self) -> None:
        copilot = provider_environment.SPEC_BY_NAME["COPILOT_GITHUB_TOKEN"]
        gemini = provider_environment.SPEC_BY_NAME["GEMINI_API_KEY"]
        self.assertIn("personal-access-tokens", copilot.source)
        self.assertIn("aistudio.google.com", gemini.source)
        self.assertTrue(copilot.sensitive)
        self.assertTrue(gemini.sensitive)

    def test_refresh_preserves_runtime_added_environment_contracts(self) -> None:
        install_runtime_completion_extensions()
        specs = provider_environment.refresh_specs()
        names = {item.name for item in specs}
        self.assertIn("RASAI_AI_EXCHANGE_LOG_MAX_BYTES", names)
        self.assertIn("RASAI_PRESENTATION_TIMEZONE", names)
        self.assertIn("RASAI_APDEX_ACQUISITION_MODE", names)
        self.assertEqual(names, set(provider_environment.ENV_NAMES))
        self.assertEqual(serp_provider_ids(), provider_environment.SPEC_BY_NAME[SERP_PROVIDER_ENV].accepted)


if __name__ == "__main__":
    unittest.main()

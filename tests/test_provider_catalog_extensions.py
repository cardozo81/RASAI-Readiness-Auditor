from __future__ import annotations

import json
import unittest
from urllib.parse import parse_qs, urlsplit

from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import build_semantic_provider
from rasai.search_intelligence.config import provider_key_env
from rasai.search_intelligence.models import QueryOrigin, SerpQueryRequest
from rasai.search_intelligence.provider_catalog import (
    free_serp_provider_ids,
    serp_provider_registration,
)
from rasai.search_intelligence.providers.scrapingdog import ScrapingDogProvider
from rasai.search_intelligence.providers.zenserp import ZenserpProvider
from rasai.search_intelligence.runtime import live_provider_ids


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def request(*, device: str = "desktop", depth: int = 10) -> SerpQueryRequest:
    return SerpQueryRequest(
        query="seguro auto",
        engine="google",
        country="BR",
        region="Porto Alegre, RS, Brazil",
        language="pt-BR",
        device=device,
        depth=depth,
        domain_of_interest="client.example",
        run_id="RUN-1",
        query_origin=QueryOrigin.MANUAL,
    )


class ProviderCatalogTests(unittest.TestCase):
    def test_free_serp_catalog_is_runtime_aligned(self):
        self.assertEqual(
            {"serpapi", "serpapi-bing", "zenserp", "scrapingdog"},
            set(free_serp_provider_ids()),
        )
        self.assertEqual(set(free_serp_provider_ids()), set(live_provider_ids()))
        for provider_id in free_serp_provider_ids():
            registration = serp_provider_registration(provider_id)
            self.assertTrue(registration.credential_url.startswith("https://"))
            self.assertTrue(registration.documentation_url.startswith("https://"))
            self.assertTrue(registration.free_tier_note)
            self.assertEqual(registration.key_env, provider_key_env(provider_id))

    def test_copilot_is_explicit_only_with_onboarding_metadata(self):
        registration = get_provider_registration("copilot")
        self.assertIsNotNone(registration)
        self.assertEqual("COPILOT", registration.provider_name)
        self.assertEqual("COPILOT_GITHUB_TOKEN", registration.key_env)
        self.assertTrue(registration.explicit_only)
        self.assertFalse(registration.auto_eligible)
        self.assertIn("github.com/settings/personal-access-tokens", registration.credential_url)
        provider = build_semantic_provider("copilot", env={})
        self.assertEqual("COPILOT", provider.name)
        self.assertIsNone(provider.api_key)

    def test_console_environment_catalog_imports_with_copilot(self):
        from rasai.console_environment import environment_specs

        specs = {item.name: item for item in environment_specs()}
        spec = specs["COPILOT_GITHUB_TOKEN"]
        self.assertIn("github.com/settings/personal-access-tokens", spec.source)
        self.assertTrue(spec.sensitive)


class FreeSerpAdapterTests(unittest.TestCase):
    def test_zenserp_normalizes_organic_and_sends_provider_context(self):
        calls = []
        payload = {
            "organic": [
                {"position": 1, "url": "https://leader.example/", "title": "Leader", "description": "A"},
                {"position": 2, "url": "https://client.example/", "title": "Client", "description": "B"},
            ]
        }

        def opener(req, timeout):
            calls.append(req)
            return FakeResponse(payload)

        provider = ZenserpProvider(
            api_key="zen-secret", retries=0, min_interval_seconds=0, opener=opener
        )
        response = provider.observe(request())
        self.assertEqual((1, 2), tuple(item.position for item in response.observation.results))
        self.assertEqual("client.example", response.observation.results[1].domain)
        self.assertEqual("zen-secret", calls[0].headers["Apikey"])
        params = parse_qs(urlsplit(calls[0].full_url).query)
        self.assertEqual(["google"], params["engine"])
        self.assertEqual(["BR"], params["gl"])
        self.assertEqual(["desktop"], params["device"])
        self.assertNotIn("zen-secret", calls[0].full_url)

    def test_scrapingdog_normalizes_rank_and_mobile_credit_metadata(self):
        calls = []
        payload = {
            "organic_results": [
                {"rank": 1, "link": "https://leader.example/", "title": "Leader", "snippet": "A"},
                {"rank": 2, "link": "https://client.example/", "title": "Client", "snippet": "B"},
            ]
        }

        def opener(req, timeout):
            calls.append(req)
            return FakeResponse(payload)

        provider = ScrapingDogProvider(
            api_key="dog-secret", retries=0, min_interval_seconds=0, opener=opener
        )
        response = provider.observe(request(device="mobile"))
        self.assertEqual((1, 2), tuple(item.position for item in response.observation.results))
        self.assertEqual(10, response.observation.quality_metadata["credit_cost_per_request"])
        params = parse_qs(urlsplit(calls[0].full_url).query)
        self.assertEqual(["dog-secret"], params["api_key"])
        self.assertEqual(["true"], params["mob_search"])
        self.assertEqual(["br"], params["country"])


if __name__ == "__main__":
    unittest.main()

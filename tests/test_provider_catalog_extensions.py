from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from rasai.copilot_provider import GitHubCopilotProvider, _prompt_from_payload
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

    def test_copilot_bridges_provider_neutral_technical_payload_without_tools(self):
        prompt = _prompt_from_payload(
            {
                "model": "auto",
                "instructions": "Return JSON only and cite evidence EV-1.",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "EV-1"}]}],
                "text": {"format": {"type": "json_schema", "schema": {"type": "object"}}},
            }
        )
        self.assertIn("Return JSON only", prompt)
        self.assertIn("EV-1", prompt)
        self.assertIn("json_schema", prompt)
        self.assertIn("Never browse", prompt)
        self.assertNotIn('"model":"auto"', prompt)

    def test_copilot_transport_uses_documented_python_sdk_shape(self):
        captured: dict[str, object] = {}

        class FakeSession:
            async def send_and_wait(self, prompt, timeout):
                captured["prompt"] = prompt
                captured["timeout"] = timeout
                return types.SimpleNamespace(
                    data=types.SimpleNamespace(content='{"ok":true}')
                )

            async def disconnect(self):
                captured["disconnected"] = True

        class FakeCopilotClient:
            def __init__(self, options):
                captured["client_options"] = options

            async def start(self):
                captured["started"] = True

            async def create_session(self, **kwargs):
                captured["session_kwargs"] = kwargs
                return FakeSession()

            async def stop(self):
                captured["stopped"] = True

        fake_module = types.ModuleType("copilot")
        fake_module.CopilotClient = FakeCopilotClient
        provider = GitHubCopilotProvider(api_key="github_pat_test")
        body = json.dumps({"model": "auto", "prompt": "Return JSON only"}).encode("utf-8")
        with patch.dict(sys.modules, {"copilot": fake_module}):
            response = provider._copilot_transport("copilot://sdk", {}, body, 17.0)

        self.assertEqual({"output_text": '{"ok":true}'}, response)
        self.assertEqual(
            {"github_token": "github_pat_test", "use_logged_in_user": False},
            captured["client_options"],
        )
        self.assertEqual(
            {"model": "auto", "available_tools": []},
            captured["session_kwargs"],
        )
        self.assertEqual("Return JSON only", captured["prompt"])
        self.assertEqual(17.0, captured["timeout"])
        self.assertTrue(captured["started"])
        self.assertTrue(captured["stopped"])
        self.assertTrue(captured["disconnected"])

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

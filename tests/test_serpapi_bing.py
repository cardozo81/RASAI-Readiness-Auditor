from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from rasai.search_intelligence.budget import RequestBudget
from rasai.search_intelligence.cli import _render_result, main as search_main
from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.models import DomainMatchStatus, QueryOrigin, SerpQueryRequest
from rasai.search_intelligence.monitoring import SearchMonitorQuery
from rasai.search_intelligence.monitoring_cli import _estimate
from rasai.search_intelligence.providers.serpapi_bing import SerpApiBingProvider
from rasai.search_intelligence.runtime import (
    live_provider_ids,
    projected_http_request_ceiling,
    validate_live_provider_engine,
)
from rasai.search_intelligence.service import SearchIntelligenceService


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def request(*, depth: int = 10, domain: str = "client.example") -> SerpQueryRequest:
    return SerpQueryRequest(
        query="seguro residencial",
        engine="bing",
        country="BR",
        region="Porto Alegre, RS, Brazil",
        language="pt-BR",
        device="desktop",
        depth=depth,
        domain_of_interest=domain,
        run_id="RUN-BING-1",
        query_origin=QueryOrigin.MANUAL,
    )


class SerpApiBingTests(unittest.TestCase):
    def test_runtime_registers_bing_without_changing_google_adapter_id(self):
        self.assertIn("serpapi", live_provider_ids())
        self.assertIn("serpapi-bing", live_provider_ids())

    def test_dynamic_pagination_uses_provider_first_cursor_and_absolute_positions(self):
        first = {
            "search_metadata": {"id": "bing-1", "created_at": "2026-09-09 12:00:00 UTC"},
            "organic_results": [
                {"position": 1, "link": "https://leader-1.example/"},
                {"position": 2, "link": "https://leader-2.example/"},
                {"position": 3, "link": "https://leader-3.example/"},
                {"position": 4, "link": "https://leader-4.example/"},
            ],
            "serpapi_pagination": {
                "next": "https://serpapi.com/search.json?engine=bing&q=x&first=5"
            },
        }
        second = {
            "search_metadata": {"id": "bing-2", "created_at": "2026-09-09 12:00:01 UTC"},
            "organic_results": [
                {"position": 1, "link": "https://leader-5.example/"},
                {"position": 2, "link": "https://leader-6.example/"},
                {"position": 3, "link": "https://client.example/page"},
                {"position": 4, "link": "https://leader-8.example/"},
                {"position": 5, "link": "https://leader-9.example/"},
                {"position": 6, "link": "https://leader-10.example/"},
            ],
        }
        calls = []

        def opener(req, timeout):
            params = parse_qs(urlsplit(req.full_url).query)
            calls.append(params)
            payload = second if params.get("first") == ["5"] else first
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        budget = RequestBudget(10)
        provider = SerpApiBingProvider(
            api_key="SECRETKEY",
            retries=0,
            min_interval_seconds=0,
            budget=budget,
            opener=opener,
        )
        result = SearchIntelligenceService(provider=provider).observe(request())

        self.assertEqual(DomainMatchStatus.FOUND, result.domain_status)
        self.assertEqual(7, result.customer_position)
        self.assertEqual((1, 2, 3, 4, 5, 6), tuple(item.position for item in result.results_ahead))
        self.assertEqual(2, len(calls))
        self.assertNotIn("first", calls[0])
        self.assertEqual(["5"], calls[1]["first"])
        self.assertEqual(["bing"], calls[0]["engine"])
        self.assertEqual(["pt-BR"], calls[0]["mkt"])
        self.assertEqual(["Porto Alegre, RS, Brazil"], calls[0]["location"])
        self.assertEqual(["desktop"], calls[0]["device"])
        self.assertTrue(result.observation.quality_metadata["requested_depth_complete"])
        self.assertEqual(10, result.observation.quality_metadata["observed_position_ceiling"])
        self.assertEqual(2, budget.used)

    def test_budget_limited_partial_observation_never_becomes_false_not_found(self):
        payload = {
            "search_metadata": {"id": "bing-1"},
            "organic_results": [
                {"position": 1, "link": "https://leader-1.example/"},
                {"position": 2, "link": "https://leader-2.example/"},
                {"position": 3, "link": "https://leader-3.example/"},
                {"position": 4, "link": "https://leader-4.example/"},
            ],
            "serpapi_pagination": {
                "next_link": "https://serpapi.com/search.json?engine=bing&q=x&first=5"
            },
        }

        def opener(req, timeout):
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        budget = RequestBudget(1)
        provider = SerpApiBingProvider(
            api_key="SECRETKEY",
            retries=0,
            min_interval_seconds=0,
            budget=budget,
            opener=opener,
        )
        result = SearchIntelligenceService(provider=provider).observe(request(depth=10))

        self.assertEqual(DomainMatchStatus.UNAVAILABLE, result.domain_status)
        self.assertEqual("SERP_REQUESTED_DEPTH_INCOMPLETE", result.error_code)
        self.assertFalse(result.observation.quality_metadata["requested_depth_complete"])
        self.assertTrue(
            result.observation.quality_metadata["request_budget_ended_before_requested_depth"]
        )
        self.assertEqual(1, budget.used)

    def test_variable_pagination_console_output_never_renders_none_ceiling(self):
        payload = {
            "search_metadata": {"id": "bing-console"},
            "organic_results": [
                {"position": 1, "link": "https://leader.example/"},
                {"position": 2, "link": "https://client.example/page"},
                {"position": 3, "link": "https://other.example/"},
                {"position": 4, "link": "https://another.example/"},
            ],
        }

        def opener(req, timeout):
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        provider = SerpApiBingProvider(
            api_key="x", retries=0, min_interval_seconds=0, opener=opener
        )
        result = SearchIntelligenceService(provider=provider).observe(request(depth=4))
        output = io.StringIO()
        with redirect_stdout(output):
            _render_result(result)
        rendered = output.getvalue()
        self.assertIn("Páginas provider coletadas: 1 (paginação variável)", rendered)
        self.assertNotIn("/None", rendered)

    def test_bing_adapter_rejects_google_before_network(self):
        calls = []

        def opener(req, timeout):
            calls.append(1)
            return FakeResponse(b"{}")

        provider = SerpApiBingProvider(
            api_key="x", retries=0, min_interval_seconds=0, opener=opener
        )
        req = SerpQueryRequest(
            query="x",
            engine="google",
            country="BR",
            language="pt-BR",
            device="desktop",
            depth=10,
            domain_of_interest="client.example",
        )
        result = SearchIntelligenceService(provider=provider).observe(req)
        self.assertEqual(DomainMatchStatus.ERROR, result.domain_status)
        self.assertEqual("SERP_UNSUPPORTED_ENGINE", result.error_code)
        self.assertEqual([], calls)

    def test_bing_dry_run_ceiling_is_one_global_hard_budget_for_multiple_queries(self):
        config = SerpRuntimeConfig(
            mode="live", provider="serpapi-bing", max_requests=13, retries=1
        ).validate()
        self.assertEqual(
            13,
            projected_http_request_ceiling(config, depths=(20, 20, 10)),
        )

    def test_provider_engine_preflight_rejects_mismatch_without_network(self):
        validate_live_provider_engine("serpapi-bing", "bing")
        validate_live_provider_engine("serpapi", "google")
        with self.assertRaisesRegex(ValueError, "does not support engine"):
            validate_live_provider_engine("serpapi-bing", "google")
        with self.assertRaisesRegex(ValueError, "does not support engine"):
            validate_live_provider_engine("serpapi", "bing")

    def test_point_in_time_cli_bing_dry_run_uses_global_budget(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"RASAI_SERP_MAX_REQUESTS": "13"}, clear=True):
            with redirect_stdout(output):
                result = search_main(
                    [
                        "seguro residencial",
                        "--domain",
                        "client.example",
                        "--engine",
                        "bing",
                        "--provider",
                        "serpapi-bing",
                        "--mode",
                        "live",
                        "--depth",
                        "20",
                        "--dry-run",
                    ]
                )
        self.assertEqual(0, result)
        self.assertIn("SERP HTTP request ceiling: 13/13", output.getvalue())
        self.assertIn("No provider, content or AI call executed.", output.getvalue())

    def test_search_monitor_dry_run_estimate_uses_same_global_budget(self):
        item = SearchMonitorQuery(
            query_id="SQRY-BING",
            project_id="PROJ-1",
            property_id="PROP-1",
            environment_id="ENV-1",
            query="seguro residencial",
            domain_of_interest="client.example",
            engine="bing",
            requested_depth=20,
            mode="live",
            provider="serpapi-bing",
        )
        with patch.dict(os.environ, {"RASAI_SERP_MAX_REQUESTS": "11"}, clear=True):
            serp, content, ai = _estimate(item)
        self.assertEqual((11, 0, 0), (serp, content, ai))


if __name__ == "__main__":
    unittest.main()

"""Tests for additive runtime completion extensions."""
from __future__ import annotations

import sqlite3
import unittest

from rasai.m18_ai import ProviderErrorClass, ProviderState
from rasai.provider_extensions import GeminiProvider
from rasai.runtime_completion_extensions import install_runtime_completion_extensions


class RuntimeCompletionExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_runtime_completion_extensions()

    def test_executive_dashboard_contains_all_lighthouse_category_cards(self) -> None:
        from rasai import rasai_readiness_reporting as reporting

        data = {
            "scores": [],
            "web_run": None,
            "web": [
                {
                    "device": "MOBILE",
                    "cwv_assessment": "PASS",
                    "performance_score": 90.0,
                    "accessibility_score": 91.0,
                    "best_practices_score": 92.0,
                    "seo_score": 93.0,
                    "agentic_browsing_score": 94.0,
                },
                {
                    "device": "DESKTOP",
                    "cwv_assessment": "PASS",
                    "performance_score": 95.0,
                    "accessibility_score": 96.0,
                    "best_practices_score": 97.0,
                    "seo_score": 98.0,
                    "agentic_browsing_score": 99.0,
                },
            ],
            "apdex_run": None,
            "apdex": [],
        }
        html = reporting._dashboard(data, __import__("pathlib").Path("."))
        self.assertIn("Lighthouse Performance", html)
        self.assertIn("Lighthouse Accessibility", html)
        self.assertIn("Lighthouse Best Practices", html)
        self.assertIn("Lighthouse SEO técnico", html)
        self.assertIn("Lighthouse Agentic Browsing", html)
        self.assertIn("experimental", html)

    def test_monitoring_reads_best_practices_and_agentic_scores(self) -> None:
        from rasai.monitoring import reader

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute(
                """
                CREATE TABLE web_performance_observations(
                    audit_id TEXT,device TEXT,url TEXT,captured_at TEXT,
                    performance_score REAL,accessibility_score REAL,best_practices_score REAL,
                    seo_score REAL,agentic_browsing_score REAL,
                    lcp_lab_ms REAL,tbt_lab_ms REAL,cls_lab REAL,
                    lcp_p75_ms REAL,inp_p75_ms REAL,cls_p75 REAL,
                    field_source TEXT,field_scope TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO web_performance_observations VALUES (
                    'AUD-X','MOBILE','https://example.test/','2026-09-10T12:00:00Z',
                    90,91,92,93,94,1000,100,0.01,1200,120,0.02,'CRUX_API','URL'
                )
                """
            )
        signals = {}
        reader._read_performance(
            connection,
            {"web_performance_observations"},
            "AUD-X",
            signals,
        )
        connection.close()
        best = "PERF|MOBILE|https://example.test/|best_practices_score"
        agentic = "PERF|MOBILE|https://example.test/|agentic_browsing_score"
        self.assertEqual(signals[best].value, 92.0)
        self.assertEqual(signals[agentic].value, 94.0)
        self.assertEqual(signals[agentic].label, "Lighthouse Agentic Browsing")

    def test_agentic_browsing_has_explicit_external_provenance(self) -> None:
        from rasai import indicator_provenance

        items = [
            item
            for item in indicator_provenance.INDICATORS
            if "Agentic Browsing" in item.indicator
        ]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].classification, "EXTERNAL_DEFINED_METRIC")
        self.assertEqual(items[0].score_role, "CONTEXT_ONLY")

    def test_gemini_embedded_error_is_classified_and_keeps_provider_code(self) -> None:
        provider = GeminiProvider(
            model="gemini-3.8-flash",
            api_key="test",
            transport=lambda *_: {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "message": "quota",
                }
            },
        )
        result = provider.analyze(_semantic_input())
        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertIsNotNone(result.diagnostic)
        self.assertEqual(result.diagnostic.error_class, ProviderErrorClass.RATE_LIMIT_ERROR)
        self.assertEqual(result.diagnostic.http_status, 429)
        self.assertEqual(result.diagnostic.error_type, "RESOURCE_EXHAUSTED")
        self.assertEqual(result.diagnostic.error_code, "RATE_LIMIT_EXCEEDED")


def _semantic_input():
    from rasai.semantic import SemanticEvidenceInput, SemanticInput

    return SemanticInput(
        snapshot_id="S1",
        page_url="https://example.test/",
        title="Fixture",
        main_content="Fixture content",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(
            SemanticEvidenceInput(
                evidence_id="EV-1",
                evidence_type="TEXT_EXCERPT",
                source="test",
                observed_value={"text": "Fixture"},
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()

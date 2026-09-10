from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from rasai.dynamic_ai_routing import DynamicProviderRoutingSession
from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.runtime_adherence_extensions import (
    _enrich_serp_reports,
    _install_dynamic_provider_contract,
    _scope_experience_config,
    _serp_issue_category,
)


class RuntimeAdherenceExtensionsTests(unittest.TestCase):
    @staticmethod
    def _experience(mix: tuple[tuple[str, float], ...]) -> ExperienceApdexConfig:
        return ExperienceApdexConfig(
            enabled=True,
            target_samples_per_page=100,
            max_attempts_per_page=125,
            max_pages=1,
            device_mix=mix,
            session_mode="cold",
            kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=3.0,
            frustrated_threshold_seconds=12.0,
            errors_affect_apdex=True,
            error_scope="first-party",
            settle_seconds=5.0,
            delay_seconds=1.0,
            concurrency=1,
        ).validate()

    def test_mobile_scope_forces_100_percent_mobile(self) -> None:
        config = self._experience((("MOBILE", 60.0), ("DESKTOP", 35.0), ("TABLET", 5.0)))
        scoped = _scope_experience_config(config, "mobile")
        self.assertEqual(scoped.device_mix_dict(), {"MOBILE": 100.0})

    def test_desktop_scope_forces_100_percent_desktop(self) -> None:
        config = self._experience((("MOBILE", 60.0), ("DESKTOP", 35.0), ("TABLET", 5.0)))
        scoped = _scope_experience_config(config, "desktop")
        self.assertEqual(scoped.device_mix_dict(), {"DESKTOP": 100.0})

    def test_both_scope_drops_tablet_and_renormalizes_core_devices(self) -> None:
        config = self._experience((("MOBILE", 60.0), ("DESKTOP", 35.0), ("TABLET", 5.0)))
        scoped = _scope_experience_config(config, "both")
        mix = scoped.device_mix_dict()
        self.assertNotIn("TABLET", mix)
        self.assertAlmostEqual(mix["MOBILE"], 60.0 / 95.0 * 100.0)
        self.assertAlmostEqual(mix["DESKTOP"], 35.0 / 95.0 * 100.0)
        self.assertAlmostEqual(sum(mix.values()), 100.0)

    def test_serp_errors_are_classified_for_operator_diagnostics(self) -> None:
        self.assertEqual(
            _serp_issue_category("SERP_PROVIDER_ERROR", "SerpApi HTTP 402: no credits left"),
            "BUSINESS_CREDIT_OR_BILLING",
        )
        self.assertEqual(
            _serp_issue_category("SERP_PROVIDER_ERROR", "SerpApi HTTP 401: invalid api key"),
            "BUSINESS_AUTHENTICATION_OR_PERMISSION",
        )
        self.assertEqual(
            _serp_issue_category("SERP_PROVIDER_TIMEOUT", "provider timed out"),
            "TECHNICAL_TIMEOUT",
        )
        self.assertEqual(
            _serp_issue_category("SERP_PROVIDER_ERROR", "SerpApi HTTP 503"),
            "TECHNICAL_TRANSIENT_PROVIDER",
        )

    def test_serp_report_highlights_customer_position_and_limitations_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            search_path = report / "search-intelligence.html"
            index_path = report / "index.html"
            base = "<!doctype html><html><body><header><h1>RASAi</h1></header></body></html>"
            search_path.write_text(base, encoding="utf-8")
            index_path.write_text(base, encoding="utf-8")
            issues = [
                {
                    "query": "seguro auto",
                    "provider": "serpapi",
                    "error_code": "SERP_PROVIDER_ERROR",
                    "error_message": "SerpApi HTTP 402: no credits left",
                }
            ]
            found = [
                {
                    "query": "seguro residencial",
                    "domain_of_interest": "loja.example.com",
                    "customer_position": 7,
                }
            ]

            _enrich_serp_reports(root, issues, found)
            _enrich_serp_reports(root, issues, found)

            search_html = search_path.read_text(encoding="utf-8")
            index_html = index_path.read_text(encoding="utf-8")
            self.assertIn("Domínio principal localizado", search_html)
            self.assertIn("posição <strong>#7</strong>", search_html)
            self.assertIn("BUSINESS_CREDIT_OR_BILLING", search_html)
            self.assertIn("SerpApi HTTP 402: no credits left", search_html)
            self.assertIn("Search Intelligence concluído com limitações", index_html)
            self.assertEqual(search_html.count("RASAI_SERP_RUNTIME_ADHERENCE_START"), 1)
            self.assertEqual(index_html.count("RASAI_SERP_RUNTIME_ADHERENCE_START"), 1)

    def test_dynamic_auto_router_exposes_semantic_provider_name_contract(self) -> None:
        _install_dynamic_provider_contract()
        session = DynamicProviderRoutingSession(())
        self.assertEqual(session.name, "AUTO")


if __name__ == "__main__":
    unittest.main()

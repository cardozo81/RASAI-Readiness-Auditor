from __future__ import annotations

import unittest

from searchgeo.source_quality import RedirectDetail, SourceQualityAssessment, SourceQualityIssue, _report_block
from searchgeo.source_quality_browser import (
    BrowserRouteObservation,
    _recovered_issue,
    browser_reconciliation_limitations,
    SourceQualityBrowserReconciliation,
)


class SecureRedirectRecoveryTests(unittest.TestCase):
    def _issue(self) -> SourceQualityIssue:
        return SourceQualityIssue(
            requested_url="https://mdsgroup.com/",
            final_url="https://mds.pt/",
            http_status=None,
            network_error="TLS",
            network_error_message="certificate verify failed: hostname mismatch for mds.pt",
            redirects=(
                RedirectDetail(
                    status=301,
                    source_url="https://mdsgroup.com/",
                    location="http://www.mdsgroup.com/",
                    target_url="http://www.mdsgroup.com/",
                ),
                RedirectDetail(
                    status=301,
                    source_url="http://www.mdsgroup.com/",
                    location="https://mds.pt/",
                    target_url="https://mds.pt/",
                ),
            ),
            hard_blocker=True,
            severity="CRITICAL",
            classification="TLS_CERTIFICATE_ERROR",
            deterministic_summary="A rota original terminou em erro TLS.",
            recommended_actions=("Corrigir a rota publicada.",),
            cross_host_redirect=True,
            http_downgrade_hop=True,
        )

    def _observation(self) -> BrowserRouteObservation:
        return BrowserRouteObservation(
            requested_url="https://mdsgroup.com/",
            final_url="https://www.mdsgroup.com/pt/",
            http_status=200,
            device="DESKTOP",
            secure_recovery=True,
            recovery_candidate_url="https://www.mdsgroup.com/",
        )

    def test_recovered_issue_is_explicit_and_preserves_original_failure_context(self) -> None:
        recovered = _recovered_issue(self._issue(), (self._observation(),))
        self.assertFalse(recovered.hard_blocker)
        self.assertEqual(recovered.classification, "HTTPS_DOWNGRADE_SECURE_RECOVERY")
        self.assertEqual(recovered.final_url, "https://www.mdsgroup.com/pt/")
        self.assertEqual(recovered.http_status, 200)
        self.assertIsNone(recovered.network_error)
        self.assertIsNone(recovered.network_error_message)
        self.assertIn("https://www.mdsgroup.com/", recovered.deterministic_summary)
        self.assertIn("https://mds.pt/", recovered.deterministic_summary)
        self.assertIn("validação TLS ativa", recovered.deterministic_summary)
        self.assertIn("não corrige o servidor", recovered.deterministic_summary)
        self.assertTrue(any("sem hop intermediário HTTP" in item for item in recovered.recommended_actions))
        self.assertTrue(recovered.http_downgrade_hop)

    def test_limitations_explain_that_audit_continued_but_redirect_still_requires_fix(self) -> None:
        recovered = _recovered_issue(self._issue(), (self._observation(),))
        reconciliation = SourceQualityBrowserReconciliation(
            assessment=SourceQualityAssessment(
                issues=(recovered,),
                pages_considered=1,
                hard_blocked_pages=0,
            ),
            recovered_urls=("https://mdsgroup.com/",),
            unresolved_urls=(),
            browser_observations=(self._observation(),),
        )
        limitations = browser_reconciliation_limitations(reconciliation)
        self.assertEqual(len(limitations), 1)
        self.assertIn("HTTPS", limitations[0])
        self.assertIn("HTTP", limitations[0])
        self.assertIn("rota segura", limitations[0])
        self.assertIn("corrigido", limitations[0])

    def test_report_shows_recovered_final_url_and_original_301_chain(self) -> None:
        recovered = _recovered_issue(self._issue(), (self._observation(),))
        html = _report_block(
            SourceQualityAssessment(
                issues=(recovered,),
                pages_considered=1,
                hard_blocked_pages=0,
            ),
            None,
        )
        self.assertIn("HTTPS_DOWNGRADE_SECURE_RECOVERY", html)
        self.assertIn("https://www.mdsgroup.com/pt/", html)
        self.assertIn("https://www.mdsgroup.com/", html)
        self.assertIn("http://www.mdsgroup.com/", html)
        self.assertIn("https://mds.pt/", html)
        self.assertGreaterEqual(html.count("301"), 2)
        self.assertIn("validação TLS ativa", html)
        self.assertNotIn("ignore_https_errors", html)


if __name__ == "__main__":
    unittest.main()

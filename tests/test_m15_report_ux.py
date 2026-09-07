from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from rasai.domain import (
    Audit,
    AuditTarget,
    DeviceContext,
    DiscoverySource,
    Evidence,
    EvidenceType,
    Finding,
    FindingDevice,
    Page,
    RuleExecution,
    RuleResult,
    Severity,
    TargetType,
)
from rasai.m14_persistence import M14Persistence
from rasai.m15_reporting import M15RemediationReportBuilder, M15ReportBuilder, _short_path
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


class M15ReportUxTests(unittest.TestCase):
    def test_short_path_hides_domain_and_keeps_query(self) -> None:
        self.assertEqual(_short_path("https://example.com/"), "/")
        self.assertEqual(_short_path("https://example.com/catalog/item?q=abc"), "/catalog/item?q=abc")

    def test_remediation_groups_same_rule_across_pages_and_separates_global_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-M15")
            page1 = "https://example.com/catalog/a"
            page2 = "https://example.com/catalog/b"
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(Audit(
                    audit_id="AUD-M15", project_name="Projeto M15", auditor_version="test", ruleset_version="1"
                ))
                persistence.targets.add(AuditTarget(
                    "TGT-M15", "AUD-M15", page1, "https://example.com", TargetType.URL_SET
                ))
                persistence.pages.add(Page("PGE-A", "AUD-M15", page1, page1, (DiscoverySource.SEED,), 0))
                persistence.pages.add(Page("PGE-B", "AUD-M15", page2, page2, (DiscoverySource.MANUAL,), 0))
                with M14Persistence(workspace) as m14:
                    m14.replace_input_urls("AUD-M15", ((page1, page1), (page2, page2)))

                for suffix, page_id, device in (
                    ("A", "PGE-A", DeviceContext.DESKTOP),
                    ("B", "PGE-B", DeviceContext.MOBILE),
                ):
                    ev_id = f"EV-{suffix}"
                    rex_id = f"REX-{suffix}"
                    finding_id = f"FND-{suffix}"
                    persistence.evidence.add(Evidence(
                        evidence_id=ev_id, audit_id="AUD-M15", page_id=page_id,
                        snapshot_id=None, device=device, evidence_type=EvidenceType.DOM_ELEMENT,
                        source="fixture", observed_value={"canonicals": []}, artifact_reference=None,
                        captured_at=_NOW,
                    ))
                    persistence.rule_executions.add(RuleExecution(
                        rule_execution_id=rex_id, audit_id="AUD-M15", rule_id="BR-GEO-013",
                        rule_version="1", page_id=page_id, snapshot_id=None, device=device,
                        result=RuleResult.WARNING, observed_value={"canonicals": []},
                        expected_condition="canonical declarations are interpretable",
                        evidence_ids=(ev_id,), executed_at=_NOW,
                    ))
                    persistence.findings.add(Finding(
                        finding_id=finding_id, audit_id="AUD-M15", rule_id="BR-GEO-013",
                        rule_execution_id=rex_id, page_id=page_id,
                        device=FindingDevice.DESKTOP if device is DeviceContext.DESKTOP else FindingDevice.MOBILE,
                        category="INDEXABILITY", severity=Severity.MEDIUM, source="test",
                        title="Canonical ausente", observed_value={"canonicals": []},
                        expected_condition="canonical declarations are interpretable",
                        evidence_ids=(ev_id,), status="OPEN",
                    ))

                global_ev = "EV-G"
                persistence.evidence.add(Evidence(
                    evidence_id=global_ev, audit_id="AUD-M15", page_id=None, snapshot_id=None,
                    device=None, evidence_type=EvidenceType.ROBOTS_RULE, source="fixture",
                    observed_value={"state": "OBTAINED"}, artifact_reference=None, captured_at=_NOW,
                ))
                persistence.rule_executions.add(RuleExecution(
                    rule_execution_id="REX-G", audit_id="AUD-M15", rule_id="BR-GEO-017",
                    rule_version="1", page_id=None, snapshot_id=None, device=None,
                    result=RuleResult.WARNING, observed_value={"state": "OBTAINED"},
                    expected_condition="robots policy is interpretable", evidence_ids=(global_ev,), executed_at=_NOW,
                ))
                persistence.findings.add(Finding(
                    finding_id="FND-G", audit_id="AUD-M15", rule_id="BR-GEO-017",
                    rule_execution_id="REX-G", page_id=None, device=FindingDevice.BOTH,
                    category="ROBOTS", severity=Severity.MEDIUM, source="test",
                    title="Política de robots requer revisão", observed_value={"state": "OBTAINED"},
                    expected_condition="robots policy is interpretable", evidence_ids=(global_ev,), status="OPEN",
                ))

            html = M15RemediationReportBuilder().build(audit_id="AUD-M15", workspace=workspace)
            self.assertIn("Problemas globais", html)
            self.assertIn("Problemas por página", html)
            self.assertIn("GLOBAL", html)
            self.assertIn("PÁGINAS · 2 afetada(s)", html)
            self.assertEqual(html.count("Canonical ausente"), 1)
            self.assertIn("/catalog/a", html)
            self.assertIn("/catalog/b", html)
            self.assertNotIn("https://example.com/catalog/a", html)
            self.assertIn("report.html#pagina-1", html)
            self.assertIn("report.html#pagina-2", html)

    def test_main_ux_contains_fixed_path_navigation_score_guide_and_interpretation(self) -> None:
        sidebar = M15ReportBuilder._sidebar([
            {"normalized_url": "https://example.com/a-very-long-path-that-should-be-visually-truncated"},
            {"normalized_url": "https://example.com/second"},
        ])
        guide = M15ReportBuilder._score_dimension_guide([])
        interpretation = M15ReportBuilder._interpretation()
        self.assertIn("#pagina-1", sidebar)
        self.assertIn("/a-very-long-path", sidebar)
        self.assertNotIn("https://example.com", sidebar)
        self.assertIn("remediation.html", sidebar)
        self.assertEqual(guide.count("class='m15-guide-card'"), 10)
        self.assertIn("Acessibilidade Técnica", guide)
        self.assertIn("Dados Estruturados", guide)
        self.assertIn("Google Search Central", guide)
        self.assertIn("Coverage", interpretation)
        self.assertIn("Actionability", interpretation)
        self.assertIn("0.0 calculado", interpretation)


if __name__ == "__main__":
    unittest.main()

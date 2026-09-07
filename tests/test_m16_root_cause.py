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
    PageSnapshot,
    RuleExecution,
    RuleResult,
    Severity,
    TargetType,
)
from rasai.m14_persistence import ElementObservation, M14Persistence
from rasai.m16_reporting import M16RemediationReportBuilder, M16ReportBuilder
from rasai.m16_root_cause import M16Persistence, materialize_root_causes
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)


class M16RootCauseTests(unittest.TestCase):
    def test_materializes_exact_set_context_and_global_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            count = materialize_root_causes(audit_id="AUD-M16", workspace=workspace)
            self.assertEqual(count, 4)

            with M16Persistence(workspace) as store:
                title = store.get("FND-TITLE")
                headings = store.get("FND-HEADINGS")
                answer = store.get("FND-ANSWER")
                robots = store.get("FND-ROBOTS")

            self.assertIsNotNone(title)
            self.assertEqual(title.affected_scope, "EXACT_ELEMENT")
            self.assertEqual(title.selector_status, "EXACT")
            self.assertEqual(title.affected_elements[0].selector, "title")
            self.assertEqual(title.affected_elements[0].relation, "EXACT")
            self.assertIn("TITLE_SEMANTICS", title.cause_type)
            self.assertIn("EDIT_CONTENT", title.exact_change)

            self.assertIsNotNone(headings)
            self.assertEqual(headings.selector_status, "MULTI_ELEMENT_SET")
            self.assertEqual({item.selector for item in headings.affected_elements}, {"h1", "main > h3"})
            self.assertTrue(all(item.relation == "SET_MEMBER" for item in headings.affected_elements))

            self.assertIsNotNone(answer)
            self.assertEqual(answer.selector_status, "CONTEXT_REGION")
            self.assertEqual(answer.affected_elements[0].selector, "main")
            self.assertEqual(answer.affected_elements[0].relation, "CONTEXT_REGION")

            self.assertIsNotNone(robots)
            self.assertEqual(robots.affected_scope, "DOMAIN_RESOURCE")
            self.assertEqual(robots.selector_status, "NOT_APPLICABLE")
            self.assertEqual(robots.affected_elements, ())

    def test_both_reports_expose_root_cause_and_do_not_invent_global_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            materialize_root_causes(audit_id="AUD-M16", workspace=workspace)

            report = M16ReportBuilder().build(audit_id="AUD-M16", workspace=workspace)
            remediation = M16RemediationReportBuilder().build(audit_id="AUD-M16", workspace=workspace)

            self.assertIn("Diagnóstico de causa raiz", report)
            self.assertIn("Mudança exata recomendada", report)
            self.assertIn("title", report)
            self.assertIn("CONJUNTO DE ELEMENTOS", report)
            self.assertIn("REGIÃO CONTEXTUAL", report)

            self.assertIn("Diagnóstico técnico por ocorrência", remediation)
            self.assertIn("causa raiz", remediation)
            self.assertIn("DOMÍNIO / RECURSO GLOBAL", remediation)
            self.assertIn("NÃO APLICÁVEL", remediation)
            self.assertNotIn("DOMÍNIO / RECURSO GLOBAL</strong></div>\n        <div><small>Selector</small><strong>ELEMENTO EXATO", remediation)

    @staticmethod
    def _fixture(root: Path) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-M16")
        url = "https://example.com/produto"
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-M16", project_name="Projeto M16", auditor_version="test", ruleset_version="1"
            ))
            persistence.targets.add(AuditTarget(
                "TGT-M16", "AUD-M16", url, "https://example.com", TargetType.URL_SET
            ))
            persistence.pages.add(Page(
                "PGE-M16", "AUD-M16", url, url, (DiscoverySource.SEED,), 0
            ))
            persistence.snapshots.add(PageSnapshot(
                snapshot_id="SNP-M16", page_id="PGE-M16", device=DeviceContext.DESKTOP,
                requested_url=url, final_url=url, captured_at=_NOW, http_status=200,
                title="Genérico", rendered_artifact_ref="artifacts/rendered/example.html",
            ))

            for ev_id, page_id, snapshot_id, device, ev_type, observed in (
                ("EV-TITLE", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, EvidenceType.DOM_ELEMENT, {"title": "Genérico"}),
                ("EV-HEAD", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, EvidenceType.DOM_ELEMENT, {"headings": ["h1", "h3"]}),
                ("EV-ANSWER", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, EvidenceType.TEXT_EXCERPT, {"reason": "ANSWER_CONTEXT_GAP"}),
                ("EV-ROBOTS", None, None, None, EvidenceType.ROBOTS_RULE, {"state": "INVALID"}),
            ):
                persistence.evidence.add(Evidence(
                    evidence_id=ev_id, audit_id="AUD-M16", page_id=page_id,
                    snapshot_id=snapshot_id, device=device, evidence_type=ev_type,
                    source="fixture", observed_value=observed, artifact_reference=None,
                    captured_at=_NOW,
                ))

            cases = (
                ("TITLE", "BR-GEO-028", "EV-TITLE", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, FindingDevice.DESKTOP,
                 {"reason": "TITLE_NOT_REPRESENTATIVE"}, "Title should represent the main topic", "Título pouco representativo", "SEMANTIC_STRUCTURE"),
                ("HEADINGS", "BR-GEO-029", "EV-HEAD", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, FindingDevice.DESKTOP,
                 {"reason": "HEADING_HIERARCHY"}, "Heading hierarchy is understandable", "Hierarquia de headings", "SEMANTIC_STRUCTURE"),
                ("ANSWER", "BR-GEO-039", "EV-ANSWER", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP, FindingDevice.DESKTOP,
                 {"reason": "ANSWER_CONTEXT_GAP"}, "Primary questions receive explicit answers", "Resposta principal insuficiente", "ANSWERABILITY"),
                ("ROBOTS", "BR-GEO-017", "EV-ROBOTS", None, None, None, FindingDevice.BOTH,
                 {"state": "INVALID"}, "robots policy is interpretable", "robots.txt não interpretável", "ROBOTS"),
            )
            for suffix, rule_id, ev_id, page_id, snapshot_id, device, finding_device, observed, expected, title, category in cases:
                rex_id = f"REX-{suffix}"
                persistence.rule_executions.add(RuleExecution(
                    rule_execution_id=rex_id, audit_id="AUD-M16", rule_id=rule_id,
                    rule_version="1", page_id=page_id, snapshot_id=snapshot_id, device=device,
                    result=RuleResult.WARNING, observed_value=observed,
                    expected_condition=expected, evidence_ids=(ev_id,), executed_at=_NOW,
                ))
                persistence.findings.add(Finding(
                    finding_id=f"FND-{suffix}", audit_id="AUD-M16", rule_id=rule_id,
                    rule_execution_id=rex_id, page_id=page_id, device=finding_device,
                    category=category, severity=Severity.MEDIUM, source="fixture", title=title,
                    observed_value=observed, expected_condition=expected,
                    evidence_ids=(ev_id,), status="OPEN",
                ))

            with M14Persistence(workspace) as m14:
                m14.replace_input_urls("AUD-M16", ((url, url),))
                observations = (
                    ElementObservation(
                        "EL-TITLE", "AUD-M16", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP,
                        url, "title", "title", None, (), "<title>Genérico</title>", "Genérico",
                        {"x": 0.0, "y": 0.0, "width": 100.0, "height": 20.0}, None, _NOW,
                    ),
                    ElementObservation(
                        "EL-H1", "AUD-M16", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP,
                        url, "h1", "h1", None, (), "<h1>Produto</h1>", "Produto",
                        {"x": 10.0, "y": 100.0, "width": 300.0, "height": 40.0}, None, _NOW,
                    ),
                    ElementObservation(
                        "EL-H3", "AUD-M16", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP,
                        url, "main > h3", "h3", None, (), "<h3>Detalhe</h3>", "Detalhe",
                        {"x": 10.0, "y": 180.0, "width": 300.0, "height": 30.0}, None, _NOW,
                    ),
                    ElementObservation(
                        "EL-MAIN", "AUD-M16", "PGE-M16", "SNP-M16", DeviceContext.DESKTOP,
                        url, "main", "main", None, (), "<main>...</main>", "Conteúdo",
                        {"x": 0.0, "y": 80.0, "width": 400.0, "height": 600.0}, None, _NOW,
                    ),
                )
                for observation in observations:
                    m14.add_element_observation(observation)
                m14.link_finding("FND-TITLE", "EL-TITLE")

        return workspace


if __name__ == "__main__":
    unittest.main()

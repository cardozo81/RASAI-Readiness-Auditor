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
from rasai.m14_persistence import M14Persistence
from rasai.m16_root_cause import M16Persistence, materialize_root_causes
from rasai.m17_precision import M17PrecisionPersistence, materialize_m17_precision
from rasai.m17_reporting import M17RemediationReportBuilder, M17ReportBuilder, _ai_disclaimer
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


class M17PrecisionReportingTests(unittest.TestCase):
    def test_canonical_absence_becomes_precise_cause_and_target_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            materialize_root_causes(audit_id="AUD-M17", workspace=workspace)
            materialize_m17_precision(audit_id="AUD-M17", workspace=workspace)

            with M16Persistence(workspace) as m16:
                base = m16.get("FND-A")
            with M17PrecisionPersistence(workspace) as m17:
                precision = m17.get("FND-A")

            self.assertIsNotNone(base)
            self.assertIsNotNone(precision)
            self.assertEqual(precision.reason_code, "CANONICAL_ABSENT")
            self.assertEqual(precision.observed_element_status, "ABSENT")
            self.assertIsNone(precision.observed_selector)
            self.assertEqual(precision.target_selector, 'head > link[rel="canonical"]')
            self.assertIn("Nenhuma declaração <link", precision.precise_cause_summary)

    def test_report_distinguishes_observed_and_target_selectors_and_reduces_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            materialize_root_causes(audit_id="AUD-M17", workspace=workspace)
            materialize_m17_precision(audit_id="AUD-M17", workspace=workspace)

            report = M17ReportBuilder().build(audit_id="AUD-M17", workspace=workspace)

            self.assertIn("Findings identificados", report)
            self.assertIn("Ações necessárias", report)
            self.assertIn("Revisões recomendadas", report)
            self.assertIn("Ações e revisões prioritárias", report)
            self.assertIn("Elemento observado</small><strong>ABSENT", report)
            self.assertIn("Selector observado</small><strong>NÃO APLICÁVEL", report)
            self.assertIn("Selector técnico alvo", report)
            self.assertIn("head &gt; link[rel=&quot;canonical&quot;]", report)
            self.assertIn("Abrir detalhamento completo desta remediação", report)
            self.assertIn("Correções técnicas detalhadas", report)
            self.assertIn("Para reduzir duplicação", report)
            self.assertNotIn("<strong>Problema:</strong>", report)

    def test_remediation_groups_same_rule_across_two_pages_with_precise_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory))
            materialize_root_causes(audit_id="AUD-M17", workspace=workspace)
            materialize_m17_precision(audit_id="AUD-M17", workspace=workspace)

            html = M17RemediationReportBuilder().build(audit_id="AUD-M17", workspace=workspace)

            self.assertIn("Achados e remediações agrupados", html)
            self.assertIn("PÁGINAS · 2 afetada(s)", html)
            self.assertIn("/a", html)
            self.assertIn("/b", html)
            self.assertEqual(html.count("Motivo técnico</small><strong>CANONICAL_ABSENT"), 2)
            self.assertEqual(html.count("Selector técnico alvo"), 2)
            self.assertIn("REVISÃO RECOMENDADA", html)

    def test_ai_unavailable_copy_does_not_claim_external_analysis_completed(self) -> None:
        text = _ai_disclaimer([{"provider": "UNAVAILABLE"}])
        self.assertIn("tentativa de uso", text)
        self.assertIn("nenhuma análise semântica externa válida foi concluída", text)
        self.assertNotIn("utilizaram o provider externo", text)

    def test_orphan_fail_execution_is_exposed_as_integrity_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory), orphan_fail=True)
            materialize_root_causes(audit_id="AUD-M17", workspace=workspace)
            materialize_m17_precision(audit_id="AUD-M17", workspace=workspace)

            report = M17ReportBuilder().build(audit_id="AUD-M17", workspace=workspace)

            self.assertIn("Integridade RuleExecution → Finding: ATENÇÃO", report)
            self.assertIn("EXECUÇÃO SEM FINDING", report)
            self.assertIn("BR-GEO-005", report)

    @staticmethod
    def _fixture(root: Path, orphan_fail: bool = False) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-M17")
        urls = ("https://example.com/a", "https://example.com/b")
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-M17",
                project_name="Projeto M17",
                auditor_version="test",
                ruleset_version="1",
            ))
            persistence.targets.add(AuditTarget(
                "TGT-M17",
                "AUD-M17",
                urls[0],
                "https://example.com",
                TargetType.URL_SET,
            ))

            for suffix, url in (("A", urls[0]), ("B", urls[1])):
                page_id = f"PGE-{suffix}"
                snapshot_id = f"SNP-{suffix}"
                evidence_id = f"EV-{suffix}"
                execution_id = f"REX-{suffix}"
                finding_id = f"FND-{suffix}"
                persistence.pages.add(Page(
                    page_id,
                    "AUD-M17",
                    url,
                    url,
                    (DiscoverySource.SEED,),
                    0,
                ))
                persistence.snapshots.add(PageSnapshot(
                    snapshot_id=snapshot_id,
                    page_id=page_id,
                    device=DeviceContext.DESKTOP,
                    requested_url=url,
                    final_url=url,
                    captured_at=_NOW,
                    http_status=200,
                    title="Página",
                    rendered_artifact_ref="artifacts/rendered/example.html",
                ))
                persistence.evidence.add(Evidence(
                    evidence_id=evidence_id,
                    audit_id="AUD-M17",
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.HTML_ELEMENT,
                    source="rules:BR-GEO-013",
                    observed_value={
                        "result": "WARNING",
                        "observed": {"canonicals": []},
                        "checks": [],
                        "reason": "CANONICAL_ABSENT",
                    },
                    artifact_reference=None,
                    captured_at=_NOW,
                ))
                persistence.rule_executions.add(RuleExecution(
                    rule_execution_id=execution_id,
                    audit_id="AUD-M17",
                    rule_id="BR-GEO-013",
                    rule_version="1",
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.WARNING,
                    observed_value={"canonicals": []},
                    expected_condition="canonical declarations are interpretable and non-conflicting",
                    evidence_ids=(evidence_id,),
                    executed_at=_NOW,
                ))
                persistence.findings.add(Finding(
                    finding_id=finding_id,
                    audit_id="AUD-M17",
                    rule_id="BR-GEO-013",
                    rule_execution_id=execution_id,
                    page_id=page_id,
                    device=FindingDevice.DESKTOP,
                    category="INDEXABILITY",
                    severity=Severity.MEDIUM,
                    source="fixture",
                    title="Canonical declarations must be interpretable and non-conflicting",
                    observed_value={"canonicals": []},
                    expected_condition="canonical declarations are interpretable and non-conflicting",
                    evidence_ids=(evidence_id,),
                    status="OPEN",
                ))

            if orphan_fail:
                persistence.evidence.add(Evidence(
                    evidence_id="EV-ORPHAN",
                    audit_id="AUD-M17",
                    page_id="PGE-A",
                    snapshot_id="SNP-A",
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.HTTP_RESPONSE,
                    source="fixture",
                    observed_value={"status": 500},
                    artifact_reference=None,
                    captured_at=_NOW,
                ))
                persistence.rule_executions.add(RuleExecution(
                    rule_execution_id="REX-ORPHAN",
                    audit_id="AUD-M17",
                    rule_id="BR-GEO-005",
                    rule_version="1",
                    page_id="PGE-A",
                    snapshot_id="SNP-A",
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.FAIL,
                    observed_value={"status": 500},
                    expected_condition="page is recoverable",
                    evidence_ids=("EV-ORPHAN",),
                    executed_at=_NOW,
                ))

        with M14Persistence(workspace) as m14:
            m14.replace_input_urls("AUD-M17", tuple((url, url) for url in urls))
        return workspace


if __name__ == "__main__":
    unittest.main()

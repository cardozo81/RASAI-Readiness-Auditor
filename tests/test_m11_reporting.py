"""Critical Actionable GEO Remediation Report tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from rasai.domain import (
    Audit,
    AuditMode,
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
)
from rasai.m10 import execute_m10
from rasai.m11 import execute_m11
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.prioritization import (
    Effort,
    Impact,
    PriorityClass,
    PriorityConfidence,
    Recommendation,
    RemediationGroup,
)
from rasai.recommendation_persistence import RecommendationPersistence
from rasai.reporting import ReportPersistence, TEMPLATE_VERSION
from rasai.scoring import (
    ConsolidationStatus,
    Score,
    ScoreConfidence,
    SCORING_VERSION,
)
from rasai.scoring_persistence import ScoringPersistence


_NOW = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)


class M11ReportingTests(unittest.TestCase):
    def test_report_is_self_contained_ptbr_traceable_and_redacts_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-1")
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(
                    Audit(
                        audit_id="AUD-1",
                        project_name="Projeto Exemplo",
                        audit_mode=AuditMode.NO_AI,
                        capabilities=("NO_AI", "FILESYSTEM", "SQLITE"),
                        limitations=("Universo limitado por max_pages configurado.",),
                        auditor_version="0.1.0",
                        ruleset_version="RULESET-1",
                    )
                )
                evidence = Evidence(
                    evidence_id="EVD-1",
                    audit_id="AUD-1",
                    page_id=None,
                    snapshot_id=None,
                    device=None,
                    evidence_type=EvidenceType.HTTP_RESPONSE,
                    source="test-http",
                    observed_value={
                        "status": 503,
                        "authorization": "Bearer super-secret-value",
                    },
                    artifact_reference=None,
                    captured_at=_NOW,
                )
                persistence.evidence.add(evidence)
                execution = RuleExecution(
                    rule_execution_id="REX-1",
                    audit_id="AUD-1",
                    rule_id="BR-GEO-005",
                    rule_version="1",
                    page_id=None,
                    snapshot_id=None,
                    device=None,
                    result=RuleResult.FAIL,
                    observed_value={"status": 503},
                    expected_condition="target is technically retrievable",
                    evidence_ids=("EVD-1",),
                    executed_at=_NOW,
                )
                persistence.rule_executions.add(execution)
                finding = Finding(
                    finding_id="FND-1",
                    audit_id="AUD-1",
                    rule_id="BR-GEO-005",
                    rule_execution_id="REX-1",
                    page_id=None,
                    device=FindingDevice.BOTH,
                    category="TECHNICAL_ACCESSIBILITY",
                    severity=Severity.CRITICAL,
                    source="deterministic-rules-engine",
                    title="Destino indisponível",
                    observed_value={"status": 503},
                    expected_condition="target is technically retrievable",
                    evidence_ids=("EVD-1",),
                    status="OPEN",
                )
                persistence.findings.add(finding)

                with ScoringPersistence(workspace) as scoring:
                    scoring.add_score(
                        Score(
                            score_id="SCR-1",
                            audit_id="AUD-1",
                            dimension="TECHNICAL_ACCESSIBILITY",
                            device=DeviceContext.DESKTOP,
                            value=50.0,
                            coverage=0.75,
                            confidence=ScoreConfidence.MEDIUM,
                            consolidation_status=ConsolidationStatus.PARTIAL,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=("coverage parcial",),
                        )
                    )
                    scoring.add_score(
                        Score(
                            score_id="SCR-OVERALL",
                            audit_id="AUD-1",
                            dimension="OVERALL_READINESS",
                            device=DeviceContext.DESKTOP,
                            value=None,
                            coverage=0.30,
                            confidence=ScoreConfidence.LOW,
                            consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=("dimensões insuficientes",),
                        )
                    )

                group = RemediationGroup(
                    group_id="RMG-1",
                    rule_id="BR-GEO-005",
                    root_cause="BR-GEO-005:TECHNICAL_ACCESSIBILITY:target is technically retrievable",
                    affected_findings=("FND-1",),
                    affected_pages=(),
                    devices=(FindingDevice.BOTH,),
                    severity=Severity.CRITICAL,
                    impact=Impact.VERY_HIGH,
                    confidence=PriorityConfidence.HIGH,
                    effort=Effort.LOW,
                    priority_score=90.5,
                    priority_class=PriorityClass.P0,
                )
                recommendation = Recommendation(
                    recommendation_id="REC-1",
                    audit_id="AUD-1",
                    finding_id=None,
                    remediation_group_id="RMG-1",
                    device=FindingDevice.BOTH,
                    title="Corrigir acessibilidade e indexabilidade",
                    description="Restabelecer resposta HTTP utilizável e revalidar.",
                    impact=Impact.VERY_HIGH,
                    effort=Effort.LOW,
                    confidence=PriorityConfidence.HIGH,
                    priority_score=90.5,
                    priority_class=PriorityClass.P0,
                )
                with RecommendationPersistence(workspace) as recommendations:
                    recommendations.add_group(audit_id="AUD-1", group=group)
                    recommendations.add_recommendation(recommendation)

                result = execute_m11(
                    audit_id="AUD-1", persistence=persistence, workspace=workspace
                )

            html = (workspace.root / "report.html").read_text(encoding="utf-8")
            self.assertTrue(html.startswith("<!doctype html>"))
            self.assertIn('lang="pt-BR"', html)
            self.assertIn("Como interpretar este relatório", html)
            self.assertIn("Acessibilidade Técnica", html)
            self.assertIn("NÃO CONSOLIDADO", html)
            self.assertIn("Destino indisponível", html)
            self.assertIn("EVD-1", html)
            self.assertIn("Corrigir acessibilidade e indexabilidade", html)
            self.assertIn("Algumas avaliações semânticas não foram executadas", html)
            self.assertIn("[REDACTED]", html)
            self.assertNotIn("super-secret-value", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("<script", html.lower())
            self.assertEqual(result.file_path, "report.html")
            self.assertEqual(result.template_version, TEMPLATE_VERSION)
            with ReportPersistence(workspace) as reports:
                reopened = reports.get(result.report_id)
                self.assertIsNotNone(reopened)
                assert reopened is not None
                self.assertEqual(reopened.file_path, "report.html")
                self.assertEqual(reopened.template_version, TEMPLATE_VERSION)

    def test_dynamic_text_is_html_escaped_and_optional_sections_remain_honest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-X")
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(
                    Audit(
                        audit_id="AUD-X",
                        project_name="<script>alert('x')</script>",
                        auditor_version="0.1.0",
                        ruleset_version="RULESET-1",
                    )
                )
                execute_m11(
                    audit_id="AUD-X", persistence=persistence, workspace=workspace
                )
            html = (workspace.root / "report.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", html)
            self.assertIn("&lt;script&gt;alert", html)
            self.assertIn("Nenhum score persistido disponível", html)
            self.assertIn("Nenhum finding persistido", html)
            self.assertIn("Nenhuma recomendação persistida", html)
            self.assertIn("O produto mede readiness", html)
            self.assertIn("Não promete ranking, citação, visibilidade", html)

    def test_actionable_report_separates_score_coverage_confidence_and_renders_canonical_crawl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-ACTION")
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(
                    Audit(
                        audit_id="AUD-ACTION",
                        project_name="Actionable Fixture",
                        max_pages=1,
                        audit_mode=AuditMode.NO_AI,
                        capabilities=("filesystem", "sqlite", "NO_AI"),
                        limitations=(
                            "MAX_PAGES_REACHED:discovered=4;audited=1",
                            "AI_NOT_CONFIGURED",
                        ),
                        auditor_version="0.1.0",
                        ruleset_version="1",
                    )
                )
                page = Page(
                    page_id="PGE-1",
                    audit_id="AUD-ACTION",
                    normalized_url="https://example.com/produto",
                    discovered_url="https://example.com/produto",
                    discovery_sources=(DiscoverySource.SEED,),
                    depth=0,
                )
                persistence.pages.add(page)

                canonical_evidence = Evidence(
                    evidence_id="EV-CANONICAL",
                    audit_id="AUD-ACTION",
                    page_id="PGE-1",
                    snapshot_id=None,
                    device=None,
                    evidence_type=EvidenceType.HTML_ELEMENT,
                    source="rules:BR-GEO-013",
                    observed_value={
                        "result": "WARNING",
                        "observed": {"canonicals": []},
                        "reason": "CANONICAL_ABSENT",
                    },
                    artifact_reference=None,
                    captured_at=_NOW,
                )
                persistence.evidence.add(canonical_evidence)
                canonical_execution = RuleExecution(
                    rule_execution_id="REX-CANONICAL",
                    audit_id="AUD-ACTION",
                    rule_id="BR-GEO-013",
                    rule_version="1",
                    page_id="PGE-1",
                    snapshot_id=None,
                    device=None,
                    result=RuleResult.WARNING,
                    observed_value={"canonicals": []},
                    expected_condition=(
                        "canonical declarations are interpretable and non-conflicting; "
                        "absence is surfaced conservatively"
                    ),
                    evidence_ids=("EV-CANONICAL",),
                    executed_at=_NOW,
                )
                persistence.rule_executions.add(canonical_execution)
                persistence.findings.add(
                    Finding(
                        finding_id="FND-CANONICAL",
                        audit_id="AUD-ACTION",
                        rule_id="BR-GEO-013",
                        rule_execution_id="REX-CANONICAL",
                        page_id="PGE-1",
                        device=FindingDevice.BOTH,
                        category="INDEXABILITY",
                        severity=Severity.MEDIUM,
                        source="deterministic-rules-engine",
                        title="Canonical ausente",
                        observed_value={"canonicals": []},
                        expected_condition=canonical_execution.expected_condition,
                        evidence_ids=("EV-CANONICAL",),
                        status="OPEN",
                    )
                )

                persistence.evidence.add(
                    Evidence(
                        evidence_id="EV-ROBOTS",
                        audit_id="AUD-ACTION",
                        page_id=None,
                        snapshot_id=None,
                        device=None,
                        evidence_type=EvidenceType.ROBOTS_RULE,
                        source="https://example.com/robots.txt",
                        observed_value={
                            "state": "OBTAINED",
                            "declared_sitemaps": ["https://example.com/sitemap.xml"],
                            "crawler_access": {},
                        },
                        artifact_reference=None,
                        captured_at=_NOW,
                    )
                )
                persistence.evidence.add(
                    Evidence(
                        evidence_id="EV-SITEMAP",
                        audit_id="AUD-ACTION",
                        page_id=None,
                        snapshot_id=None,
                        device=None,
                        evidence_type=EvidenceType.SITEMAP_ENTRY,
                        source="https://example.com/sitemap.xml",
                        observed_value={
                            "state": "OBTAINED",
                            "page_urls": ["https://example.com/produto"],
                            "child_sitemaps": [],
                            "error": None,
                        },
                        artifact_reference=None,
                        captured_at=_NOW,
                    )
                )

                with ScoringPersistence(workspace) as scoring:
                    scoring.add_score(
                        Score(
                            score_id="SCR-D-INDEX",
                            audit_id="AUD-ACTION",
                            dimension="INDEXABILITY",
                            device=DeviceContext.DESKTOP,
                            value=75.0,
                            coverage=1.0,
                            confidence=ScoreConfidence.HIGH,
                            consolidation_status=ConsolidationStatus.CONSOLIDATED,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=(),
                        )
                    )
                    scoring.add_score(
                        Score(
                            score_id="SCR-M-INDEX",
                            audit_id="AUD-ACTION",
                            dimension="INDEXABILITY",
                            device=DeviceContext.MOBILE,
                            value=48.0,
                            coverage=0.60,
                            confidence=ScoreConfidence.LOW,
                            consolidation_status=ConsolidationStatus.PARTIAL,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=("coverage parcial",),
                        )
                    )
                    scoring.add_score(
                        Score(
                            score_id="SCR-D-OVERALL",
                            audit_id="AUD-ACTION",
                            dimension="OVERALL_READINESS",
                            device=DeviceContext.DESKTOP,
                            value=82.0,
                            coverage=0.92,
                            confidence=ScoreConfidence.MEDIUM,
                            consolidation_status=ConsolidationStatus.CONSOLIDATED,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=(),
                        )
                    )
                    scoring.add_score(
                        Score(
                            score_id="SCR-M-OVERALL",
                            audit_id="AUD-ACTION",
                            dimension="OVERALL_READINESS",
                            device=DeviceContext.MOBILE,
                            value=None,
                            coverage=0.27,
                            confidence=ScoreConfidence.LOW,
                            consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                            scoring_version=SCORING_VERSION,
                            calculated_at=_NOW,
                            limitations=("dimensões insuficientes",),
                        )
                    )

                execute_m10(
                    audit_id="AUD-ACTION",
                    finding_ids=("FND-CANONICAL",),
                    persistence=persistence,
                    workspace=workspace,
                )
                execute_m11(
                    audit_id="AUD-ACTION",
                    persistence=persistence,
                    workspace=workspace,
                )

            html = (workspace.root / "report.html").read_text(encoding="utf-8")
            self.assertIn("Readiness Search & AI", html)
            self.assertIn("RESULTADOS CONSOLIDADOS POR DISPOSITIVO", html)
            self.assertIn("82.0", html)
            self.assertIn("Alta", html)
            self.assertIn("NÃO DETERMINADA", html)
            self.assertIn("Cobertura da análise", html)
            self.assertIn("Confiabilidade", html)
            self.assertIn("Score GEO - Desktop", html)
            self.assertIn("Score GEO - Mobile", html)
            self.assertIn("Corrigir declaração canonical", html)
            self.assertIn("Nenhuma declaração canonical válida foi encontrada.", html)
            self.assertIn("&lt;link rel=&quot;canonical&quot;&gt;", html)
            self.assertIn("URL-PREFERENCIAL", html)
            self.assertIn("Trecho HTML original não persistido para esta evidência.", html)
            self.assertIn("Critério de aceite", html)
            self.assertIn("Como revalidar", html)
            self.assertIn("Cobertura do Crawl", html)
            self.assertIn("URLs descobertas", html)
            self.assertIn("Limite atingido", html)
            self.assertIn("Sim", html)
            self.assertIn("OBTAINED", html)
            self.assertNotIn('<link rel="canonical" href="https://URL-PREFERENCIAL', html)


if __name__ == "__main__":
    unittest.main()

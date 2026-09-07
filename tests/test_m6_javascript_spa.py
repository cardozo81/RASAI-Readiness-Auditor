"""Risk-oriented tests for M6 - JavaScript / SPA."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.acquisition import HttpAcquisitionResult
from rasai.discovery import DiscoveredPage, DiscoveryResult, RobotsResult, RobotsState
from rasai.domain import (
    ArchitectureClassification,
    Audit,
    DeviceContext,
    DiscoverySource,
    Page,
    PageSnapshot,
    RuleExecution,
    RuleResult,
    new_id,
)
from rasai.javascript_spa import JavascriptSpaAnalyzer
from rasai.m2 import M2ExecutionResult
from rasai.m3 import M3ExecutionResult
from rasai.m4 import M4ExecutionResult
from rasai.m5 import M5ExecutionResult
from rasai.m6 import execute_m6
from rasai.persistence import AuditPersistence, AuditWorkspace


_NOW = datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc)


class M6JavascriptSpaTests(unittest.TestCase):
    def test_raw_shell_plus_rendered_content_is_valid_csr_spa(self) -> None:
        analyzer = JavascriptSpaAnalyzer()
        raw = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
        rendered = '<html><head><title>App</title></head><body><main><h1>Produto</h1><p>Conteúdo carregado.</p></main></body></html>'
        comparison = analyzer.compare(raw, rendered)
        self.assertEqual(comparison.architecture, ArchitectureClassification.CSR_SPA)
        self.assertFalse(comparison.raw_main_content)
        self.assertTrue(comparison.rendered_main_content)
        self.assertIn("main_content", comparison.changed_fields)

    def test_soft404_and_non_crawlable_navigation_require_strong_evidence(self) -> None:
        analyzer = JavascriptSpaAnalyzer()
        error_html = '<html><head><title>404 Not Found</title></head><body><main>Página não encontrada</main></body></html>'
        self.assertTrue(analyzer.soft404(http_status=200, rendered_html=error_html))
        self.assertFalse(analyzer.soft404(http_status=404, rendered_html=error_html))
        normal = '<html><head><title>404 ideias de SEO</title></head><body><main>Artigo válido</main></body></html>'
        self.assertFalse(analyzer.soft404(http_status=200, rendered_html=normal))

        nav = analyzer.navigation(
            '<nav><a href="/ok">OK</a><button onclick="router.go(\'/bad\')">Bad</button></nav>',
            base_url="https://example.test/",
            origin="https://example.test",
        )
        self.assertEqual(nav.crawlable_internal_links, ("https://example.test/ok",))
        self.assertEqual(nav.non_crawlable_navigation_controls, 1)

        role_nav = analyzer.navigation(
            '<div role="navigation"><button onclick="go()">Inside</button></div><button onclick="outside()">Outside</button>',
            base_url="https://example.test/",
            origin="https://example.test",
        )
        self.assertEqual(role_nav.non_crawlable_navigation_controls, 1)

    def test_lazy_content_recovered_by_bounded_probe_is_not_failed(self) -> None:
        analyzer = JavascriptSpaAnalyzer()
        initial = '<html><body><main></main><img loading="lazy" data-src="hero.jpg"></body></html>'
        after = '<html><body><main>Conteúdo essencial recuperado</main><img src="hero.jpg"></body></html>'
        assessment = analyzer.lazy_loading(initial, after_probe_html=after)
        self.assertTrue(assessment.has_lazy_signals)
        self.assertEqual(assessment.result, RuleResult.PASS)
        self.assertTrue(assessment.after_probe_content_recoverable)

    def test_execute_m6_persists_architecture_rules_and_evidence_backed_finding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit = Audit(audit_id=audit_id, project_name="M6 test")
                persistence.audits.add(audit)
                url = "https://example.test/app"
                page = Page(
                    page_id=new_id("PGE"), audit_id=audit_id, normalized_url=url,
                    discovered_url=url, discovery_sources=(DiscoverySource.SEED,), depth=0,
                )
                persistence.pages.add(page)
                raw = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
                rendered = '<html><head><title>App</title></head><body><nav><a href="/ok">OK</a><button onclick="go()">Bad</button></nav><main><h1>App</h1>Conteúdo renderizado</main></body></html>'
                raw_path = workspace.artifacts / "raw.html"
                rendered_path = workspace.artifacts / "rendered.html"
                raw_path.write_text(raw, encoding="utf-8")
                rendered_path.write_text(rendered, encoding="utf-8")
                snapshot = PageSnapshot(
                    snapshot_id=new_id("SNP"), page_id=page.page_id, device=DeviceContext.DESKTOP,
                    requested_url=url, final_url=url, captured_at=_NOW, http_status=200,
                    content_type="text/html", raw_artifact_ref=raw_path.relative_to(workspace.root).as_posix(),
                    rendered_artifact_ref=rendered_path.relative_to(workspace.root).as_posix(),
                )
                persistence.snapshots.add(snapshot)

                acquisition = HttpAcquisitionResult(
                    requested_url=url, final_url=url, status=200,
                    headers=(("Content-Type", "text/html"),), body=raw.encode(), redirects=(), network_error=None, elapsed_ms=1,
                )
                robots_acq = HttpAcquisitionResult(
                    requested_url="https://example.test/robots.txt", final_url="https://example.test/robots.txt", status=404,
                    headers=(), body=b"", redirects=(), network_error=None, elapsed_ms=1,
                )
                discovery = DiscoveryResult(
                    origin="https://example.test",
                    pages=(DiscoveredPage(url, url, (DiscoverySource.SEED,), 0, 0),),
                    page_acquisitions={url: acquisition}, provenance=(),
                    robots=RobotsResult("https://example.test/robots.txt", RobotsState.ABSENT, robots_acq, (), {url: {}}),
                    sitemaps=(), total_discovered=1, total_audited=1, max_pages=100, limit_reached=False,
                )
                m2 = M2ExecutionResult(discovery, {url: page.page_id}, {url: snapshot.raw_artifact_ref}, (), ())
                m3 = M3ExecutionResult({page.page_id: {DeviceContext.DESKTOP: snapshot.snapshot_id}}, ())
                m4 = M4ExecutionResult({snapshot.snapshot_id: ()}, ())

                prior_ids: list[str] = []
                for rule_id in ("BR-GEO-005", "BR-GEO-006", "BR-GEO-009"):
                    execution = RuleExecution(
                        rule_execution_id=new_id("REX"), audit_id=audit_id, rule_id=rule_id,
                        rule_version="1", page_id=page.page_id, snapshot_id=None, device=None,
                        result=RuleResult.PASS, observed_value={}, expected_condition="fixture", evidence_ids=(), executed_at=_NOW,
                    )
                    persistence.rule_executions.add(execution)
                    prior_ids.append(execution.rule_execution_id)
                m5 = M5ExecutionResult(tuple(prior_ids), (), tuple(f"BR-GEO-{i:03d}" for i in range(1, 19)))

                result = execute_m6(
                    audit_id=audit_id, m2_result=m2, m3_result=m3, m4_result=m4,
                    m5_result=m5, persistence=persistence, workspace=workspace,
                    lazy_probe=lambda _url, _device: self.fail("lazy probe must not run without lazy signals"),
                )

                self.assertEqual(result.architecture_by_snapshot[snapshot.snapshot_id], ArchitectureClassification.CSR_SPA)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                by_rule = {item.rule_id: item for item in executions if item}
                self.assertEqual(by_rule["BR-GEO-019"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-020"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-021"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-022"].result, RuleResult.WARNING)
                self.assertEqual(by_rule["BR-GEO-023"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-024"].result, RuleResult.PASS)
                finding = next(
                    persistence.findings.get(item) for item in result.finding_ids
                    if persistence.findings.get(item).rule_id == "BR-GEO-022"
                )
                self.assertTrue(finding.evidence_ids)
                self.assertEqual(persistence.evidence.get(finding.evidence_ids[0]).snapshot_id, snapshot.snapshot_id)

            with AuditPersistence(AuditWorkspace.open(workspace.root)) as reopened:
                stored = reopened.snapshots.get(snapshot.snapshot_id)
                self.assertEqual(stored.architecture_classification, ArchitectureClassification.CSR_SPA)


if __name__ == "__main__":
    unittest.main()

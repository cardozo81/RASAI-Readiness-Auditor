"""Focused contract tests for M14 multi-URL, visual/DOM evidence and actionability."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.acquisition import HttpAcquisitionResult
from rasai.actionability import Actionability, classify_actionability
from rasai.cli import _audit_targets
from rasai.discovery import (
    DiscoveredPage,
    DiscoveryEngine,
    DiscoveryProvenance,
    DiscoveryResult,
    RobotsResult,
    RobotsState,
)
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
from rasai.m3 import execute_m3
from rasai.m11 import execute_m11
from rasai.m14_discovery import discover_url_set
from rasai.m14_linking import link_findings_to_elements
from rasai.m14_persistence import ElementObservation, M14Persistence, sanitize_element_observation
from rasai.m14_reporting import TEMPLATE_VERSION
from rasai.m2 import M2ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import BrowserRenderResult, RenderedElementObservation
from rasai.scoring import ConsolidationStatus, Score, ScoreConfidence, SCORING_VERSION
from rasai.scoring_persistence import ScoringPersistence


_NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)
_PNG = b"\x89PNG\r\n\x1a\nM14-fixture"


def _http(url: str, *, status: int = 200, body: bytes = b"") -> HttpAcquisitionResult:
    return HttpAcquisitionResult(
        requested_url=url,
        final_url=url,
        status=status,
        headers=(("Content-Type", "text/html; charset=utf-8"),),
        body=body,
        redirects=(),
        network_error=None,
        elapsed_ms=1,
    )


class _CountingHttpClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def acquire(self, url: str) -> HttpAcquisitionResult:
        self.counts[url] = self.counts.get(url, 0) + 1
        if url == "https://example.com/robots.txt":
            return _http(
                url,
                body=(
                    b"User-agent: *\nAllow: /\n"
                    b"Sitemap: https://example.com/sitemap.xml\n"
                ),
            )
        if url == "https://example.com/sitemap.xml":
            return _http(
                url,
                body=(
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    b'<url><loc>https://example.com/</loc></url>'
                    b'<url><loc>https://example.com/produto</loc></url>'
                    b'</urlset>'
                ),
            )
        return _http(url, body=b"<html><main><h1>Fixture</h1></main></html>")


class _FakeRenderer:
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            rendered_html="<html><head><title>Produto</title></head><body><main><h1>Produto</h1></main></body></html>",
            browser_metadata={
                "engine": "chromium",
                "profile": {
                    "device": device.value,
                    "viewport": {"width": 1440 if device is DeviceContext.DESKTOP else 412, "height": 900 if device is DeviceContext.DESKTOP else 915},
                },
            },
            screenshot_png=_PNG,
            element_observations=(
                RenderedElementObservation(
                    selector="title",
                    tag_name="title",
                    element_id=None,
                    classes=(),
                    outer_html="<title>Produto</title>",
                    text_excerpt="Produto",
                    bounding_box=None,
                ),
                RenderedElementObservation(
                    selector="main > h1",
                    tag_name="h1",
                    element_id=None,
                    classes=(),
                    outer_html="<h1>Produto</h1>",
                    text_excerpt="Produto",
                    bounding_box={"x": 40.0, "y": 120.0, "width": 260.0, "height": 48.0},
                ),
            ),
        )


class M14UrlSetTests(unittest.TestCase):
    def test_explicit_url_set_is_deduplicated_and_domain_resources_are_acquired_once(self) -> None:
        client = _CountingHttpClient()
        engine = DiscoveryEngine(http_client=client)
        result = discover_url_set(
            engine,
            (
                "https://example.com/",
                "https://example.com/",
                "https://example.com/produto",
            ),
            max_pages=10,
        )
        self.assertEqual(tuple(page.normalized_url for page in result.pages), (
            "https://example.com/", "https://example.com/produto"
        ))
        self.assertEqual(result.pages[0].discovery_sources, (DiscoverySource.SEED,))
        self.assertEqual(result.pages[1].discovery_sources, (DiscoverySource.MANUAL,))
        self.assertEqual(client.counts["https://example.com/robots.txt"], 1)
        self.assertEqual(client.counts["https://example.com/sitemap.xml"], 1)
        self.assertEqual(client.counts["https://example.com/"], 1)
        self.assertEqual(client.counts["https://example.com/produto"], 1)

    def test_explicit_url_set_rejects_mixed_origin_and_does_not_start_acquisition(self) -> None:
        client = _CountingHttpClient()
        engine = DiscoveryEngine(http_client=client)
        with self.assertRaisesRegex(ValueError, "same normalized origin"):
            discover_url_set(
                engine,
                ("https://example.com/", "https://other.example/produto"),
                max_pages=10,
            )
        self.assertEqual(client.counts, {})

    def test_urls_file_and_direct_targets_share_the_same_cli_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text("# conjunto\nhttps://example.com/a\n\nhttps://example.com/b\n", encoding="utf-8")
            args = Namespace(target=["https://example.com/"], urls_file=str(path))
            self.assertEqual(
                _audit_targets(args),
                ("https://example.com/", "https://example.com/a", "https://example.com/b"),
            )


class M14EvidenceTests(unittest.TestCase):
    def _workspace_with_page(self, directory: str) -> tuple[AuditWorkspace, M2ExecutionResult]:
        workspace = AuditWorkspace.create(Path(directory), "AUD-M14")
        url = "https://example.com/produto"
        acquisition = _http(url)
        discovery = DiscoveryResult(
            origin="https://example.com",
            pages=(DiscoveredPage(url, url, (DiscoverySource.SEED,), 0, 0),),
            page_acquisitions={url: acquisition},
            provenance=(DiscoveryProvenance(url, DiscoverySource.SEED, None, url),),
            robots=RobotsResult(
                url="https://example.com/robots.txt",
                state=RobotsState.ABSENT,
                acquisition=_http("https://example.com/robots.txt", status=404),
                sitemap_urls=(),
                crawler_access={url: {"Googlebot": True, "OAI-SearchBot": True, "GPTBot": True}},
            ),
            sitemaps=(),
            total_discovered=1,
            total_audited=1,
            max_pages=10,
            limit_reached=False,
        )
        result = M2ExecutionResult(
            discovery=discovery,
            page_ids={url: "PGE-1"},
            raw_artifact_refs={url: None},
            evidence_ids=(),
            rule_execution_ids=(),
        )
        return workspace, result

    def test_m3_persists_desktop_mobile_png_and_element_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace, m2 = self._workspace_with_page(directory)
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(Audit(audit_id="AUD-M14", project_name="M14", auditor_version="test", ruleset_version="1"))
                persistence.pages.add(Page("PGE-1", "AUD-M14", "https://example.com/produto", "https://example.com/produto", (DiscoverySource.SEED,), 0))
                result = execute_m3(m2, persistence, workspace, renderer=_FakeRenderer())

                self.assertEqual(set(result.snapshot_ids["PGE-1"]), {DeviceContext.DESKTOP, DeviceContext.MOBILE})
                for device in (DeviceContext.DESKTOP, DeviceContext.MOBILE):
                    ref = result.visual_artifact_refs["PGE-1"][device]
                    self.assertIsNotNone(ref)
                    assert ref is not None
                    self.assertTrue((workspace.root / ref).is_file())
                    self.assertTrue((workspace.root / ref).read_bytes().startswith(b"\x89PNG"))

                with M14Persistence(workspace) as m14:
                    desktop = m14.list_for_snapshot(result.snapshot_ids["PGE-1"][DeviceContext.DESKTOP])
                    self.assertEqual({item.selector for item in desktop}, {"title", "main > h1"})
                    self.assertEqual(next(item for item in desktop if item.selector == "main > h1").bounding_box["width"], 260.0)

                connection = sqlite3.connect(workspace.database)
                try:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE evidence_type = 'VISUAL_SNAPSHOT'"
                    ).fetchone()[0]
                finally:
                    connection.close()
                self.assertEqual(count, 2)

    def test_element_observation_is_bounded_and_never_invents_selector(self) -> None:
        value = sanitize_element_observation(
            ElementObservation(
                element_observation_id="ELM-1",
                audit_id="AUD-1",
                page_id="PGE-1",
                snapshot_id="SNP-1",
                device=DeviceContext.DESKTOP,
                url="https://example.com/",
                selector=None,
                tag_name="H1",
                element_id=None,
                classes=("title",),
                outer_html="<h1>" + ("x" * 5000) + "\x00</h1>",
                text_excerpt="x" * 1000,
                bounding_box={"x": 1, "y": 2, "width": 3, "height": 4},
                artifact_reference="artifacts/visual/x.png",
                captured_at=_NOW,
            )
        )
        self.assertIsNone(value.selector)
        self.assertEqual(value.tag_name, "h1")
        self.assertLessEqual(len(value.outer_html or ""), 4096)
        self.assertNotIn("\x00", value.outer_html or "")
        self.assertLessEqual(len(value.text_excerpt or ""), 512)


class M14ActionabilityAndReportTests(unittest.TestCase):
    def test_actionability_keeps_result_semantics_independent(self) -> None:
        self.assertIs(classify_actionability(RuleResult.FAIL, rule_id="BR-GEO-013"), Actionability.REQUIRED_FIX)
        self.assertIs(classify_actionability(RuleResult.FAIL, rule_id="BR-GEO-012"), Actionability.REVIEW_RECOMMENDED)
        self.assertIs(classify_actionability(RuleResult.WARNING, rule_id="BR-GEO-029"), Actionability.REVIEW_RECOMMENDED)
        self.assertIs(classify_actionability(RuleResult.NOT_APPLICABLE, rule_id="BR-GEO-029"), Actionability.NO_ACTION)
        self.assertIs(classify_actionability(RuleResult.UNKNOWN, rule_id="BR-GEO-029"), Actionability.INSUFFICIENT_EVIDENCE)
        self.assertIs(classify_actionability(RuleResult.ERROR, rule_id="BR-GEO-029"), Actionability.INSUFFICIENT_EVIDENCE)
        self.assertIs(
            classify_actionability(RuleResult.WARNING, rule_id="BR-GEO-003", observed_value={"state": "ABSENT"}),
            Actionability.OPTIONAL_IMPROVEMENT,
        )

    def test_report_separates_zero_from_not_calculated_and_exposes_page_visual_dom_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-REPORT")
            url = "https://example.com/produto"
            acquisition = _http(url)
            m2 = M2ExecutionResult(
                discovery=DiscoveryResult(
                    origin="https://example.com",
                    pages=(DiscoveredPage(url, url, (DiscoverySource.SEED,), 0, 0),),
                    page_acquisitions={url: acquisition},
                    provenance=(DiscoveryProvenance(url, DiscoverySource.SEED, None, url),),
                    robots=RobotsResult(
                        url="https://example.com/robots.txt",
                        state=RobotsState.ABSENT,
                        acquisition=_http("https://example.com/robots.txt", status=404),
                        sitemap_urls=(),
                        crawler_access={url: {"Googlebot": True, "OAI-SearchBot": True, "GPTBot": True}},
                    ),
                    sitemaps=(),
                    total_discovered=1,
                    total_audited=1,
                    max_pages=10,
                    limit_reached=False,
                ),
                page_ids={url: "PGE-R"},
                raw_artifact_refs={url: None},
                evidence_ids=(),
                rule_execution_ids=(),
            )

            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(Audit(audit_id="AUD-REPORT", project_name="Projeto M14", auditor_version="test", ruleset_version="1"))
                persistence.targets.add(AuditTarget("TGT-R", "AUD-REPORT", url, "https://example.com", TargetType.URL))
                persistence.pages.add(Page("PGE-R", "AUD-REPORT", url, url, (DiscoverySource.SEED,), 0))
                with M14Persistence(workspace) as m14:
                    m14.replace_input_urls("AUD-REPORT", ((url, url),))
                m3 = execute_m3(m2, persistence, workspace, renderer=_FakeRenderer())
                snapshot_id = m3.snapshot_ids["PGE-R"][DeviceContext.DESKTOP]
                persistence.evidence.add(Evidence(
                    evidence_id="EVD-R",
                    audit_id="AUD-REPORT",
                    page_id="PGE-R",
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.DOM_ELEMENT,
                    source="fixture",
                    observed_value={"outer_html": "<title>Produto</title>"},
                    artifact_reference=None,
                    captured_at=_NOW,
                ))
                persistence.rule_executions.add(RuleExecution(
                    rule_execution_id="REX-R",
                    audit_id="AUD-REPORT",
                    rule_id="BR-GEO-028",
                    rule_version="1",
                    page_id="PGE-R",
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.FAIL,
                    observed_value={"title": "Produto"},
                    expected_condition="title is present and semantically representative of the page",
                    evidence_ids=("EVD-R",),
                    executed_at=_NOW,
                ))
                persistence.findings.add(Finding(
                    finding_id="FND-R",
                    audit_id="AUD-REPORT",
                    rule_id="BR-GEO-028",
                    rule_execution_id="REX-R",
                    page_id="PGE-R",
                    device=FindingDevice.DESKTOP,
                    category="SEMANTIC_STRUCTURE",
                    severity=Severity.HIGH,
                    source="test",
                    title="Título semanticamente insuficiente",
                    observed_value={"title": "Produto"},
                    expected_condition="title is present and semantically representative of the page",
                    evidence_ids=("EVD-R",),
                    status="OPEN",
                ))
                link_findings_to_elements(finding_ids=("FND-R",), persistence=persistence, workspace=workspace)

                with ScoringPersistence(workspace) as scoring:
                    scoring.add_score(Score(
                        score_id="SCR-D0",
                        audit_id="AUD-REPORT",
                        dimension="OVERALL_READINESS",
                        device=DeviceContext.DESKTOP,
                        value=0.0,
                        coverage=0.0,
                        confidence=ScoreConfidence.HIGH,
                        consolidation_status=ConsolidationStatus.CONSOLIDATED,
                        scoring_version=SCORING_VERSION,
                        calculated_at=_NOW,
                        limitations=(),
                    ))
                    scoring.add_score(Score(
                        score_id="SCR-MNONE",
                        audit_id="AUD-REPORT",
                        dimension="OVERALL_READINESS",
                        device=DeviceContext.MOBILE,
                        value=None,
                        coverage=0.0,
                        confidence=ScoreConfidence.UNAVAILABLE,
                        consolidation_status=ConsolidationStatus.NOT_CONSOLIDATED,
                        scoring_version=SCORING_VERSION,
                        calculated_at=_NOW,
                        limitations=("sem dados",),
                    ))

                result = execute_m11(audit_id="AUD-REPORT", persistence=persistence, workspace=workspace)

            html = (workspace.root / "report.html").read_text(encoding="utf-8")
            self.assertEqual(result.template_version, TEMPLATE_VERSION)
            self.assertIn("Score: 0.0", html)
            self.assertIn("Estado: CALCULADO", html)
            self.assertIn("Score: NÃO DETERMINADO", html)
            self.assertIn("Estado: NÃO CALCULADO", html)
            self.assertGreaterEqual(html.count("Coverage: 0%"), 2)
            self.assertIn("PÁGINA ANALISADA", html)
            self.assertIn(url, html)
            self.assertIn("AÇÃO NECESSÁRIA", html)
            self.assertIn("<strong>title</strong>", html)
            self.assertIn("&lt;title&gt;Produto&lt;/title&gt;", html)
            self.assertIn("artifacts/visual/PGE-R/desktop/", html)
            self.assertIn("WHATWG", html)
            self.assertIn("Sitemap: NÃO LOCALIZADO", html)
            self.assertIn("overflow-wrap:anywhere", html)
            self.assertNotIn("Trecho HTML original não persistido para esta evidência.", html.split("FND-R")[0] if "FND-R" in html else "")


if __name__ == "__main__":
    unittest.main()

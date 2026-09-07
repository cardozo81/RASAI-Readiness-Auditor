"""Risk-oriented tests for M5 - Deterministic Rules Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.acquisition import HttpAcquisitionResult, NetworkError, NetworkErrorKind
from rasai.discovery import (
    DiscoveredPage,
    DiscoveryResult,
    RobotsResult,
    RobotsState,
    SitemapResult,
    SitemapState,
)
from rasai.domain import (
    Audit,
    AuditTarget,
    DeviceContext,
    DiscoverySource,
    Evidence,
    EvidenceType,
    Page,
    PageSnapshot,
    RuleExecution,
    RuleResult,
    TargetType,
    new_id,
)
from rasai.m2 import M2ExecutionResult
from rasai.m3 import M3ExecutionResult
from rasai.m4 import M4ExecutionResult
from rasai.m5 import execute_m5
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rules import RuleDefinition, RuleRegistry, RuleScope, baseline_registry


_NOW = datetime(2026, 9, 2, 16, 30, tzinfo=timezone.utc)


def _acquisition(
    url: str,
    *,
    status: int | None = 200,
    body: bytes = b"<html><body>ok</body></html>",
    headers: tuple[tuple[str, str], ...] = (("Content-Type", "text/html"),),
    network_error: NetworkError | None = None,
) -> HttpAcquisitionResult:
    return HttpAcquisitionResult(
        requested_url=url,
        final_url=url if status is not None else None,
        status=status,
        headers=headers,
        body=body,
        redirects=(),
        network_error=network_error,
        elapsed_ms=1,
    )


def _fixture(
    workspace: AuditWorkspace,
    persistence: AuditPersistence,
    *,
    network_failure: bool = False,
    x_robots: str | None = None,
    meta_robots: str | None = None,
    crawler_overrides: dict[str, bool] | None = None,
) -> tuple[Audit, AuditTarget, M2ExecutionResult, M3ExecutionResult, M4ExecutionResult, str]:
    audit = Audit(audit_id=workspace.root.name, project_name="M5 test")
    url = "https://example.test/"
    target = AuditTarget(
        target_id=new_id("TGT"),
        audit_id=audit.audit_id,
        input_url=url,
        normalized_origin="https://example.test",
        target_type=TargetType.URL,
    )
    page = Page(
        page_id=new_id("PGE"),
        audit_id=audit.audit_id,
        normalized_url=url,
        discovered_url=url,
        discovery_sources=(DiscoverySource.SEED,),
        depth=0,
    )
    persistence.audits.add(audit)
    persistence.targets.add(target)
    persistence.pages.add(page)

    raw_html = '<html><head><link rel="canonical" href="https://example.test/"></head><body><main>raw content</main></body></html>'
    rendered_meta = f'<meta name="robots" content="{meta_robots}">' if meta_robots else ""
    rendered_html = f'<html><head>{rendered_meta}<link rel="canonical" href="https://example.test/"></head><body><main>rendered content</main></body></html>'
    raw_path = workspace.artifacts / "raw.html"
    rendered_path = workspace.artifacts / "rendered.html"
    main_path = workspace.artifacts / "main.txt"
    raw_path.write_text(raw_html, encoding="utf-8")
    rendered_path.write_text(rendered_html, encoding="utf-8")
    main_path.write_text("rendered content", encoding="utf-8")

    snapshot = PageSnapshot(
        snapshot_id=new_id("SNP"),
        page_id=page.page_id,
        device=DeviceContext.DESKTOP,
        requested_url=url,
        final_url=url,
        captured_at=_NOW,
        http_status=None if network_failure else 200,
        content_type="text/html",
        canonical="https://example.test/",
        meta_robots=meta_robots,
        raw_artifact_ref=raw_path.relative_to(workspace.root).as_posix(),
        rendered_artifact_ref=rendered_path.relative_to(workspace.root).as_posix(),
        main_content_ref=None if network_failure else main_path.relative_to(workspace.root).as_posix(),
    )
    persistence.snapshots.add(snapshot)

    headers: tuple[tuple[str, str], ...] = (("Content-Type", "text/html"),)
    if x_robots:
        headers += (("X-Robots-Tag", x_robots),)
    network_error = NetworkError(NetworkErrorKind.CONNECTION, "fixture") if network_failure else None
    acquisition = _acquisition(
        url,
        status=None if network_failure else 200,
        body=b"" if network_failure else raw_html.encode(),
        headers=headers,
        network_error=network_error,
    )

    crawlers = {
        "Googlebot": True,
        "Googlebot Smartphone": True,
        "Bingbot": True,
        "OAI-SearchBot": True,
        "GPTBot": True,
    }
    crawlers.update(crawler_overrides or {})
    discovery = DiscoveryResult(
        origin="https://example.test",
        pages=(DiscoveredPage(url, url, (DiscoverySource.SEED,), 0, 0),),
        page_acquisitions={url: acquisition},
        provenance=(),
        robots=RobotsResult(
            url="https://example.test/robots.txt",
            state=RobotsState.OBTAINED,
            acquisition=_acquisition("https://example.test/robots.txt", body=b"User-agent: *\nAllow: /"),
            sitemap_urls=(),
            crawler_access={url: crawlers},
        ),
        sitemaps=(
            SitemapResult(
                url="https://example.test/sitemap.xml",
                state=SitemapState.ABSENT,
                acquisition=_acquisition("https://example.test/sitemap.xml", status=404, body=b""),
            ),
        ),
        total_discovered=1,
        total_audited=1,
        max_pages=100,
        limit_reached=False,
    )

    execution_ids: list[str] = []
    for rule_id, result in (
        ("BR-GEO-002", RuleResult.PASS),
        ("BR-GEO-004", RuleResult.PASS),
        ("BR-GEO-005", RuleResult.FAIL if network_failure else RuleResult.PASS),
        ("BR-GEO-007", RuleResult.NOT_APPLICABLE if network_failure else RuleResult.PASS),
    ):
        evidence = Evidence(
            evidence_id=new_id("EV-GEO"), audit_id=audit.audit_id, page_id=page.page_id,
            snapshot_id=None, device=None, evidence_type=EvidenceType.HTTP_RESPONSE,
            source="m2-fixture", observed_value={"rule": rule_id}, artifact_reference=None, captured_at=_NOW,
        )
        persistence.evidence.add(evidence)
        execution = RuleExecution(
            rule_execution_id=new_id("REX"), audit_id=audit.audit_id, rule_id=rule_id,
            rule_version="1", page_id=page.page_id, snapshot_id=None, device=None,
            result=result, observed_value={"fixture": True}, expected_condition="fixture",
            evidence_ids=(evidence.evidence_id,), executed_at=_NOW,
        )
        persistence.rule_executions.add(execution)
        execution_ids.append(execution.rule_execution_id)

    m2 = M2ExecutionResult(
        discovery=discovery,
        page_ids={url: page.page_id},
        raw_artifact_refs={url: snapshot.raw_artifact_ref},
        evidence_ids=(),
        rule_execution_ids=tuple(execution_ids),
    )
    m3 = M3ExecutionResult(snapshot_ids={page.page_id: {DeviceContext.DESKTOP: snapshot.snapshot_id}}, failures=())
    m4 = M4ExecutionResult(evidence_ids={snapshot.snapshot_id: ()}, failures=())
    return audit, target, m2, m3, m4, snapshot.snapshot_id


class M5RulesTests(unittest.TestCase):
    def test_registry_contains_normative_001_to_018_and_rejects_duplicates(self) -> None:
        registry = baseline_registry()
        self.assertEqual(registry.ids(), tuple(f"BR-GEO-{number:03d}" for number in range(1, 19)))
        with self.assertRaises(ValueError):
            RuleRegistry(
                (
                    RuleDefinition("BR-GEO-001", "a", "x", "x", RuleScope.GLOBAL),
                    RuleDefinition("BR-GEO-001", "b", "x", "x", RuleScope.GLOBAL),
                )
            )

    def test_failed_retrievability_blocks_derivative_rules_without_cascading_failures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, target, m2, m3, m4, snapshot_id = _fixture(
                    workspace, persistence, network_failure=True
                )
                result = execute_m5(audit, target, m2, m3, m4, persistence, workspace)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                by_rule = {item.rule_id: item for item in executions if item and (item.snapshot_id == snapshot_id or item.page_id == m2.page_ids["https://example.test/"])}
                self.assertEqual(by_rule["BR-GEO-005"].result, RuleResult.FAIL)
                self.assertEqual(by_rule["BR-GEO-006"].result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(by_rule["BR-GEO-009"].result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(by_rule["BR-GEO-010"].result, RuleResult.NOT_APPLICABLE)
                findings = [persistence.findings.get(item) for item in result.finding_ids]
                self.assertIn("BR-GEO-005", {item.rule_id for item in findings if item})
                self.assertNotIn("BR-GEO-006", {item.rule_id for item in findings if item})

    def test_indexability_conflict_is_evidence_backed_and_gptbot_block_alone_does_not_penalize(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, target, m2, m3, m4, snapshot_id = _fixture(
                    workspace,
                    persistence,
                    x_robots="index",
                    meta_robots="noindex",
                    crawler_overrides={"GPTBot": False},
                )
                result = execute_m5(audit, target, m2, m3, m4, persistence, workspace)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                br011 = next(item for item in executions if item and item.rule_id == "BR-GEO-011" and item.snapshot_id == snapshot_id)
                br012 = next(item for item in executions if item and item.rule_id == "BR-GEO-012" and item.snapshot_id == snapshot_id)
                br018 = next(item for item in executions if item and item.rule_id == "BR-GEO-018")
                self.assertEqual(br011.result, RuleResult.FAIL)
                self.assertEqual(br012.result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(br018.result, RuleResult.PASS)
                finding = next(
                    persistence.findings.get(item)
                    for item in result.finding_ids
                    if persistence.findings.get(item).rule_id == "BR-GEO-011"
                )
                self.assertTrue(finding.evidence_ids)
                for evidence_id in finding.evidence_ids:
                    evidence = persistence.evidence.get(evidence_id)
                    self.assertEqual(evidence.snapshot_id, snapshot_id)

    def test_oai_searchbot_block_is_surfaced_but_not_confused_with_gptbot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, target, m2, m3, m4, _ = _fixture(
                    workspace,
                    persistence,
                    crawler_overrides={"OAI-SearchBot": False, "GPTBot": True},
                )
                result = execute_m5(audit, target, m2, m3, m4, persistence, workspace)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                br018 = next(item for item in executions if item and item.rule_id == "BR-GEO-018")
                self.assertEqual(br018.result, RuleResult.WARNING)
                self.assertEqual(br018.observed_value["blocked_search_crawlers"][0]["crawler"], "OAI-SearchBot")
                self.assertEqual(br018.observed_value["blocked_gptbot"], [])


if __name__ == "__main__":
    unittest.main()

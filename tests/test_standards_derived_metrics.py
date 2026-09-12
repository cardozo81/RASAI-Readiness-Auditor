from __future__ import annotations

from datetime import timezone
import sqlite3
import tempfile
from pathlib import Path

from rasai.domain import (
    ArchitectureClassification,
    Audit,
    AuditTarget,
    DeviceContext,
    DiscoverySource,
    Page,
    PageSnapshot,
    RuleResult,
    TargetType,
    utc_now,
)
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.standards_metrics import execute_standards_metrics, load_metrics


def _insert_rule(
    connection: sqlite3.Connection,
    *,
    execution_id: str,
    audit_id: str,
    rule_id: str,
    page_id: str | None,
    snapshot_id: str | None,
    device: str | None,
    result: str = "PASS",
) -> None:
    connection.execute(
        """INSERT INTO rule_executions (
            rule_execution_id,audit_id,rule_id,rule_version,page_id,snapshot_id,device,
            result,observed_value,expected_condition,evidence_ids,executed_at,error
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            execution_id,
            audit_id,
            rule_id,
            "1",
            page_id,
            snapshot_id,
            device,
            result,
            "{}",
            "test",
            "[]",
            utc_now().isoformat(),
            None,
        ),
    )


def test_derived_metrics_reuse_persisted_rule_executions_without_network() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = AuditWorkspace.create(Path(directory), "AUD-STANDARDS")
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-STANDARDS",
                project_name="test",
                auditor_version="test",
                ruleset_version="test",
            ))
            persistence.targets.add(AuditTarget(
                target_id="TGT-1",
                audit_id="AUD-STANDARDS",
                input_url="https://example.com/",
                normalized_origin="https://example.com",
                target_type=TargetType.DOMAIN,
            ))
            persistence.pages.add(Page(
                page_id="P-1",
                audit_id="AUD-STANDARDS",
                normalized_url="https://example.com/",
                discovered_url="https://example.com/",
                discovery_sources=(DiscoverySource.SEED, DiscoverySource.SITEMAP),
            ))
            persistence.snapshots.add(PageSnapshot(
                snapshot_id="S-1",
                page_id="P-1",
                device=DeviceContext.MOBILE,
                requested_url="https://example.com/",
                final_url="https://example.com/",
                captured_at=utc_now(),
                http_status=200,
                content_type="text/html",
                canonical="https://example.com/",
                structured_data_ref="artifacts/structured.json",
                browser_metadata={
                    "open_web_metrics": {
                        "navigation": {"ttfb_from_navigation_start_ms": 100.0}
                    }
                },
                architecture_classification=ArchitectureClassification.STATIC_OR_SSR,
            ))

        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                for index, rule_id in enumerate(("BR-GEO-005", "BR-GEO-006", "BR-GEO-009"), start=1):
                    _insert_rule(
                        connection,
                        execution_id=f"R-P-{index}",
                        audit_id="AUD-STANDARDS",
                        rule_id=rule_id,
                        page_id="P-1",
                        snapshot_id=None,
                        device=None,
                    )
                for index, rule_id in enumerate((
                    "BR-GEO-011", "BR-GEO-012", "BR-GEO-013", "BR-GEO-016",
                    "BR-GEO-034", "BR-GEO-036", "BR-GEO-037",
                ), start=1):
                    _insert_rule(
                        connection,
                        execution_id=f"R-S-{index}",
                        audit_id="AUD-STANDARDS",
                        rule_id=rule_id,
                        page_id="P-1",
                        snapshot_id="S-1",
                        device="MOBILE",
                    )
        finally:
            connection.close()

        execute_standards_metrics(
            audit_id="AUD-STANDARDS",
            workspace=workspace,
            env={
                "RASAI_DERIVED_READINESS_METRICS": "true",
                "RASAI_RETRIEVAL_METRICS": "false",
                "RASAI_W3C_VALIDATOR": "false",
                "RASAI_MDN_OBSERVATORY": "false",
                "RASAI_WEB_PLATFORM_BASELINE": "false",
                "RASAI_OPEN_WEB_METRICS": "true",
                "RASAI_PAGESPEED_ENABLED": "false",
                "RASAI_CRUX_ENABLED": "false",
                "RASAI_GSC_ENABLED": "false",
            },
        )
        metrics = {item["metric_id"]: item for item in load_metrics("AUD-STANDARDS", workspace)}
        assert metrics["crawlability_coverage"]["value"] == 100.0
        assert metrics["indexability_coverage"]["value"] == 100.0
        assert metrics["sitemap_audited_url_coverage"]["value"] == 100.0
        assert metrics["canonical_consistency_rate"]["value"] == 100.0
        assert metrics["structured_data_coverage"]["value"] == 100.0
        assert metrics["structured_data_validity_rate"]["value"] == 100.0
        assert metrics["ttfb_p95"]["value"] == 100.0

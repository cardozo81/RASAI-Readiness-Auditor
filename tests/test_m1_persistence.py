"""Risk-oriented M1 persistence tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from rasai.domain import (
    Audit,
    AuditTarget,
    CompletionStatus,
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
    new_id,
)
from rasai.persistence import AuditPersistence, AuditWorkspace


class M1PersistenceTests(unittest.TestCase):
    def test_full_m1_round_trip_and_audit_reopen(self) -> None:
        captured_at = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
        audit = Audit(
            audit_id=new_id("AUD"),
            project_name="M1 persistence test",
            primary_language="pt-BR",
            market="BR",
            max_pages=100,
            capabilities=("filesystem", "sqlite"),
            limitations=(),
            created_at=captured_at,
            auditor_version="0.1.0",
            ruleset_version="baseline",
        )
        target = AuditTarget(
            target_id=new_id("TGT"),
            audit_id=audit.audit_id,
            input_url="https://example.com",
            normalized_origin="https://example.com",
            target_type=TargetType.URL,
        )
        page = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url="https://example.com/",
            discovered_url="https://example.com/",
            discovery_sources=(DiscoverySource.SEED,),
            depth=0,
        )
        desktop_snapshot = PageSnapshot(
            snapshot_id=new_id("SNP"),
            page_id=page.page_id,
            device=DeviceContext.DESKTOP,
            requested_url=page.normalized_url,
            final_url=page.normalized_url,
            captured_at=captured_at,
            http_status=200,
            content_type="text/html",
            title="Desktop",
        )
        mobile_snapshot = PageSnapshot(
            snapshot_id=new_id("SNP"),
            page_id=page.page_id,
            device=DeviceContext.MOBILE,
            requested_url=page.normalized_url,
            final_url=page.normalized_url,
            captured_at=captured_at,
            http_status=200,
            content_type="text/html",
            title="Mobile",
        )
        evidence = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page.page_id,
            snapshot_id=desktop_snapshot.snapshot_id,
            device=DeviceContext.DESKTOP,
            evidence_type=EvidenceType.HTTP_RESPONSE,
            source="test",
            observed_value={"status": 200},
            artifact_reference="artifacts/response.html",
            captured_at=captured_at,
        )
        execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-004",
            rule_version="1",
            page_id=page.page_id,
            snapshot_id=desktop_snapshot.snapshot_id,
            device=DeviceContext.DESKTOP,
            result=RuleResult.PASS,
            observed_value={"preserved": True},
            expected_condition="HTTP acquisition artifacts preserved",
            evidence_ids=(evidence.evidence_id,),
            executed_at=captured_at,
        )
        finding = Finding(
            finding_id=new_id("FND"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-004",
            rule_execution_id=execution.rule_execution_id,
            page_id=page.page_id,
            device=FindingDevice.DESKTOP,
            category="AUDITOR_INTEGRITY",
            severity=Severity.INFO,
            source="test",
            title="Traceability fixture",
            observed_value={"preserved": True},
            expected_condition="fixture",
            evidence_ids=(evidence.evidence_id,),
            status="OPEN",
        )

        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            self.assertTrue(workspace.artifacts.is_dir())

            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(audit)
                persistence.targets.add(target)
                persistence.pages.add(page)
                persistence.snapshots.add(desktop_snapshot)
                persistence.snapshots.add(mobile_snapshot)
                persistence.evidence.add(evidence)
                persistence.rule_executions.add(execution)
                persistence.findings.add(finding)
                completed_audit = persistence.audits.complete(
                    audit.audit_id,
                    CompletionStatus.COMPLETE_WITH_LIMITATIONS,
                    completed_at=captured_at,
                )

            self.assertTrue(workspace.database.is_file())

            reopened_workspace = AuditWorkspace.open(workspace.root)
            with AuditPersistence(reopened_workspace) as persistence:
                self.assertEqual(persistence.audits.get(audit.audit_id), completed_audit)
                self.assertEqual(persistence.targets.get(target.target_id), target)
                self.assertEqual(persistence.pages.get(page.page_id), page)
                self.assertEqual(persistence.snapshots.get(desktop_snapshot.snapshot_id), desktop_snapshot)
                self.assertEqual(persistence.snapshots.get(mobile_snapshot.snapshot_id), mobile_snapshot)
                self.assertNotEqual(
                    persistence.snapshots.get(desktop_snapshot.snapshot_id).device,
                    persistence.snapshots.get(mobile_snapshot.snapshot_id).device,
                )
                self.assertEqual(persistence.evidence.get(evidence.evidence_id), evidence)
                self.assertEqual(persistence.rule_executions.get(execution.rule_execution_id), execution)
                self.assertEqual(persistence.findings.get(finding.finding_id), finding)

    def test_rejects_untraceable_references(self) -> None:
        captured_at = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
        audit = Audit(audit_id=new_id("AUD"), project_name="Integrity test")
        page_a = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url="https://example.com/a",
            discovered_url="https://example.com/a",
        )
        page_b = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url="https://example.com/b",
            discovered_url="https://example.com/b",
        )
        snapshot_a = PageSnapshot(
            snapshot_id=new_id("SNP"),
            page_id=page_a.page_id,
            device=DeviceContext.DESKTOP,
            requested_url=page_a.normalized_url,
            final_url=page_a.normalized_url,
            captured_at=captured_at,
        )
        snapshot_b = PageSnapshot(
            snapshot_id=new_id("SNP"),
            page_id=page_b.page_id,
            device=DeviceContext.DESKTOP,
            requested_url=page_b.normalized_url,
            final_url=page_b.normalized_url,
            captured_at=captured_at,
        )
        evidence_a = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page_a.page_id,
            snapshot_id=snapshot_a.snapshot_id,
            device=DeviceContext.DESKTOP,
            evidence_type=EvidenceType.HTTP_RESPONSE,
            source="test",
            observed_value={"status": 200},
            artifact_reference=None,
            captured_at=captured_at,
        )
        mismatched_evidence = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page_a.page_id,
            snapshot_id=snapshot_b.snapshot_id,
            device=DeviceContext.DESKTOP,
            evidence_type=EvidenceType.HTTP_RESPONSE,
            source="test",
            observed_value={"status": 200},
            artifact_reference=None,
            captured_at=captured_at,
        )
        evidence_b = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page_b.page_id,
            snapshot_id=snapshot_b.snapshot_id,
            device=DeviceContext.DESKTOP,
            evidence_type=EvidenceType.HTTP_RESPONSE,
            source="test",
            observed_value={"status": 200},
            artifact_reference=None,
            captured_at=captured_at,
        )

        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(audit)
                persistence.pages.add(page_a)
                persistence.pages.add(page_b)
                persistence.snapshots.add(snapshot_a)
                persistence.snapshots.add(snapshot_b)

                with self.assertRaises(sqlite3.IntegrityError):
                    persistence.evidence.add(mismatched_evidence)

                persistence.evidence.add(evidence_a)
                persistence.evidence.add(evidence_b)
                cross_page_execution = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-004",
                    rule_version="1",
                    page_id=page_a.page_id,
                    snapshot_id=snapshot_a.snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.PASS,
                    observed_value={"preserved": True},
                    expected_condition=None,
                    evidence_ids=(evidence_b.evidence_id,),
                    executed_at=captured_at,
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    persistence.rule_executions.add(cross_page_execution)

                invalid_execution = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-004",
                    rule_version="1",
                    page_id=page_a.page_id,
                    snapshot_id=snapshot_a.snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.PASS,
                    observed_value={"preserved": True},
                    expected_condition=None,
                    evidence_ids=(new_id("EV-GEO"),),
                    executed_at=captured_at,
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    persistence.rule_executions.add(invalid_execution)

                valid_execution = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-004",
                    rule_version="1",
                    page_id=page_a.page_id,
                    snapshot_id=snapshot_a.snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.PASS,
                    observed_value={"preserved": True},
                    expected_condition=None,
                    evidence_ids=(evidence_a.evidence_id,),
                    executed_at=captured_at,
                )
                persistence.rule_executions.add(valid_execution)

                unrelated_evidence = Evidence(
                    evidence_id=new_id("EV-GEO"),
                    audit_id=audit.audit_id,
                    page_id=page_a.page_id,
                    snapshot_id=snapshot_a.snapshot_id,
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.HTTP_HEADER,
                    source="test",
                    observed_value={"content-type": "text/html"},
                    artifact_reference=None,
                    captured_at=captured_at,
                )
                persistence.evidence.add(unrelated_evidence)
                invalid_finding = Finding(
                    finding_id=new_id("FND"),
                    audit_id=audit.audit_id,
                    rule_id=valid_execution.rule_id,
                    rule_execution_id=valid_execution.rule_execution_id,
                    page_id=page_a.page_id,
                    device=FindingDevice.DESKTOP,
                    category="AUDITOR_INTEGRITY",
                    severity=Severity.INFO,
                    source="test",
                    title="Invalid traceability fixture",
                    observed_value={},
                    expected_condition=None,
                    evidence_ids=(unrelated_evidence.evidence_id,),
                    status="OPEN",
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    persistence.findings.add(invalid_finding)

                wrong_device_finding = Finding(
                    finding_id=new_id("FND"),
                    audit_id=audit.audit_id,
                    rule_id=valid_execution.rule_id,
                    rule_execution_id=valid_execution.rule_execution_id,
                    page_id=page_a.page_id,
                    device=FindingDevice.MOBILE,
                    category="AUDITOR_INTEGRITY",
                    severity=Severity.INFO,
                    source="test",
                    title="Wrong device fixture",
                    observed_value={},
                    expected_condition=None,
                    evidence_ids=(evidence_a.evidence_id,),
                    status="OPEN",
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    persistence.findings.add(wrong_device_finding)

        with self.assertRaises(ValueError):
            Finding(
                finding_id=new_id("FND"),
                audit_id=audit.audit_id,
                rule_id="BR-GEO-004",
                rule_execution_id=new_id("REX"),
                page_id=page_a.page_id,
                device=FindingDevice.DESKTOP,
                category="AUDITOR_INTEGRITY",
                severity=Severity.INFO,
                source="test",
                title="No evidence",
                observed_value={},
                expected_condition=None,
                evidence_ids=(),
                status="OPEN",
            )


if __name__ == "__main__":
    unittest.main()

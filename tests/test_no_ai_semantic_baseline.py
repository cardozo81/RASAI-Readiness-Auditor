"""Regression tests for deterministic SCORE-GEO-004 semantic coverage without AI."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.domain import (
    DeviceContext,
    Evidence,
    EvidenceType,
    RuleExecution,
    RuleResult,
    new_id,
    utc_now,
)
from rasai.m4 import M4ExecutionResult
from rasai.m7 import execute_m7
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.scoring import ConsolidationStatus, ScoringEngine
from rasai.semantic import NoneProvider
from tests.test_m7_semantic_provider import _fixture


class NoAISemanticBaselineTests(unittest.TestCase):
    def test_rich_evidence_can_consolidate_score_geo_004_without_ai(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, m3, m4, m5, m6, snapshot_id, source_evidence_id = _fixture(
                    workspace,
                    persistence,
                )
                source = persistence.evidence.get(source_evidence_id)
                snapshot = persistence.snapshots.get(snapshot_id)
                self.assertIsNotNone(source)
                self.assertIsNotNone(snapshot)
                assert source is not None and snapshot is not None

                heading = Evidence(
                    evidence_id=new_id("EV-GEO"),
                    audit_id=audit.audit_id,
                    page_id=source.page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.HEADING,
                    source="baseline-regression",
                    observed_value=[
                        {"level": 1, "text": "Guia de Produto Alpha"},
                        {"level": 2, "text": "Recursos e garantia"},
                    ],
                    artifact_reference=snapshot.main_content_ref,
                    captured_at=source.captured_at,
                )
                persistence.evidence.add(heading)
                structured = Evidence(
                    evidence_id=new_id("EV-GEO"),
                    audit_id=audit.audit_id,
                    page_id=source.page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    evidence_type=EvidenceType.STRUCTURED_DATA,
                    source="baseline-regression",
                    observed_value={
                        "blocks": 1,
                        "valid_blocks": 1,
                        "invalid_blocks": 0,
                        "types": ["Product"],
                    },
                    artifact_reference=snapshot.structured_data_ref,
                    captured_at=source.captured_at,
                )
                persistence.evidence.add(structured)
                m4 = M4ExecutionResult(
                    evidence_ids={
                        snapshot_id: (
                            source_evidence_id,
                            heading.evidence_id,
                            structured.evidence_id,
                        )
                    },
                    failures=m4.failures,
                )

                result = execute_m7(
                    audit_id=audit.audit_id,
                    m3_result=m3,
                    m4_result=m4,
                    m5_result=m5,
                    m6_result=m6,
                    persistence=persistence,
                    workspace=workspace,
                    provider=NoneProvider(),
                )
                semantic_executions = tuple(
                    item
                    for execution_id in result.rule_execution_ids
                    if (item := persistence.rule_executions.get(execution_id)) is not None
                )
                unknown_rules = [
                    item.rule_id
                    for item in semantic_executions
                    if item.result is RuleResult.UNKNOWN
                ]
                self.assertEqual(unknown_rules, [])

                refreshed = persistence.audits.get(audit.audit_id)
                self.assertIsNotNone(refreshed)
                assert refreshed is not None
                self.assertIn(
                    "semantic_baseline:SEMANTIC-BASELINE-001",
                    refreshed.capabilities,
                )

                supporting = tuple(
                    RuleExecution(
                        rule_execution_id=new_id("REX"),
                        audit_id=audit.audit_id,
                        rule_id=rule_id,
                        rule_version="test",
                        page_id=source.page_id,
                        snapshot_id=snapshot_id,
                        device=DeviceContext.DESKTOP,
                        result=RuleResult.PASS,
                        observed_value={"fixture": True},
                        expected_condition="fixture",
                        evidence_ids=(source_evidence_id,),
                        executed_at=utc_now(),
                        error=None,
                    )
                    for rule_id in ("BR-GEO-005", "BR-GEO-011", "BR-GEO-025")
                )
                scoring = ScoringEngine().score(
                    audit_id=audit.audit_id,
                    executions=(*supporting, *semantic_executions),
                    devices=(DeviceContext.DESKTOP,),
                )
                overall = scoring.overall_by_device[DeviceContext.DESKTOP]
                self.assertEqual(overall.consolidation_status, ConsolidationStatus.CONSOLIDATED)
                self.assertIsNotNone(overall.value)
                self.assertGreaterEqual(overall.coverage, 0.80)


if __name__ == "__main__":
    unittest.main()

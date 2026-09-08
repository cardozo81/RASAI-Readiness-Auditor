"""Dependency isolation regression for M7 semantic rules."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.domain import AuditMode, DeviceContext, RuleExecution, RuleResult, new_id, utc_now
from rasai.m6 import M6ExecutionResult
from rasai.m7 import execute_m7
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.semantic import NoneProvider
from tests.test_m7_semantic_provider import _fixture


class M7DependencyTests(unittest.TestCase):
    def test_failed_rendered_content_blocks_semantic_derivatives_without_stale_provider_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, m3, m4, m5, _m6, snapshot_id, _ = _fixture(workspace, persistence)
                page_id = next(iter(m3.snapshot_ids))
                blocked = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-020",
                    rule_version="1",
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    device=DeviceContext.DESKTOP,
                    result=RuleResult.FAIL,
                    observed_value={"content_recoverable": False},
                    expected_condition="fixture",
                    evidence_ids=(),
                    executed_at=utc_now(),
                )
                persistence.rule_executions.add(blocked)
                m6 = M6ExecutionResult(
                    rule_execution_ids=(blocked.rule_execution_id,),
                    finding_ids=(),
                    architecture_by_snapshot={},
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
                self.assertEqual(result.audit_mode, AuditMode.NO_AI)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                by_rule = {item.rule_id: item for item in executions if item}
                self.assertEqual(by_rule["BR-GEO-028"].result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(by_rule["BR-GEO-038"].result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(by_rule["BR-GEO-049"].result, RuleResult.NOT_APPLICABLE)
                self.assertEqual(by_rule["BR-GEO-034"].result, RuleResult.PASS)
                semantic_findings = [
                    persistence.findings.get(item)
                    for item in result.finding_ids
                    if persistence.findings.get(item)
                ]
                self.assertEqual(semantic_findings, [])


if __name__ == "__main__":
    unittest.main()

"""Critical M10 prioritization and recommendation tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from rasai.domain import (
    Audit,
    Evidence,
    EvidenceType,
    Finding,
    FindingDevice,
    RuleExecution,
    RuleResult,
    Severity,
)
from rasai.m10 import execute_m10
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.prioritization import (
    Effort,
    Impact,
    PriorityClass,
    PriorityConfidence,
    PriorityEngine,
)
from rasai.recommendation_persistence import RecommendationPersistence
from rasai.remediation import recipe_for


_NOW = datetime(2026, 9, 2, 17, 30, tzinfo=timezone.utc)


def _finding(
    finding_id: str,
    *,
    rule_id: str = "BR-GEO-005",
    page_id: str | None = "P1",
    device: FindingDevice = FindingDevice.DESKTOP,
    severity: Severity = Severity.HIGH,
    category: str = "TECHNICAL_ACCESSIBILITY",
    source: str = "deterministic-rules-engine",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        audit_id="AUD-1",
        rule_id=rule_id,
        rule_execution_id=f"REX-{finding_id}",
        page_id=page_id,
        device=device,
        category=category,
        severity=severity,
        source=source,
        title="Fixture finding",
        observed_value={"fixture": True},
        expected_condition="technical condition is satisfied",
        evidence_ids=(f"EVD-{finding_id}",),
        status="OPEN",
    )


class M10PrioritizationTests(unittest.TestCase):
    def test_priority_formula_uses_unknown_effort_as_neutral_ease(self) -> None:
        score = PriorityEngine.priority_score(
            severity=Severity.MEDIUM,
            impact=Impact.MEDIUM,
            confidence=PriorityConfidence.MEDIUM,
            effort=Effort.UNKNOWN,
        )
        self.assertEqual(score, 55.25)
        self.assertEqual(
            PriorityEngine.priority_class(
                severity=Severity.MEDIUM,
                impact=Impact.MEDIUM,
                confidence=PriorityConfidence.MEDIUM,
                effort=Effort.UNKNOWN,
                category="OTHER",
            ),
            PriorityClass.P3,
        )

    def test_critical_material_access_blocker_is_p0(self) -> None:
        pclass = PriorityEngine.priority_class(
            severity=Severity.CRITICAL,
            impact=Impact.VERY_HIGH,
            confidence=PriorityConfidence.HIGH,
            effort=Effort.HIGH,
            category="TECHNICAL_ACCESSIBILITY",
        )
        self.assertEqual(pclass, PriorityClass.P0)

    def test_same_root_cause_groups_findings_and_recommends_once(self) -> None:
        result = PriorityEngine().prioritize(
            audit_id="AUD-1",
            total_pages=1,
            findings=(
                _finding("F1", device=FindingDevice.DESKTOP),
                _finding("F2", device=FindingDevice.MOBILE),
            ),
        )
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(len(result.recommendations), 1)
        group = result.groups[0]
        recommendation = result.recommendations[0]
        self.assertEqual(group.affected_findings, ("F1", "F2"))
        self.assertEqual(group.impact, Impact.VERY_HIGH)
        self.assertEqual(group.confidence, PriorityConfidence.HIGH)
        self.assertEqual(recommendation.device, FindingDevice.BOTH)
        self.assertEqual(recommendation.remediation_group_id, group.group_id)

    def test_canonical_recipe_is_actionable_and_does_not_invent_preferred_url(self) -> None:
        finding = _finding(
            "CANONICAL",
            rule_id="BR-GEO-013",
            page_id="P1",
            device=FindingDevice.BOTH,
            severity=Severity.MEDIUM,
            category="INDEXABILITY",
        )
        result = PriorityEngine().prioritize(
            audit_id="AUD-1", total_pages=1, findings=(finding,)
        )
        recommendation = result.recommendations[0]
        recipe = recipe_for("BR-GEO-013")

        self.assertEqual(recommendation.title, "Corrigir declaração canonical")
        self.assertIn("URL preferencial", recommendation.description)
        self.assertEqual(recipe.element, '<link rel="canonical">')
        self.assertEqual(recipe.location, "<head>")
        self.assertEqual(recipe.action, "ADD_OR_CORRECT")
        self.assertIn("URL-PREFERENCIAL", recipe.example or "")
        self.assertIn("Não assuma", recipe.human_decision or "")
        self.assertGreaterEqual(len(recipe.acceptance), 4)
        self.assertGreaterEqual(len(recipe.validation), 2)

    def test_execute_m10_persists_reopenable_group_and_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace.create(Path(directory), "AUD-1")
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(
                    Audit(
                        audit_id="AUD-1",
                        project_name="Fixture",
                        auditor_version="0.1",
                        ruleset_version="1",
                    )
                )
                evidence = Evidence(
                    evidence_id="EVD-1",
                    audit_id="AUD-1",
                    page_id=None,
                    snapshot_id=None,
                    device=None,
                    evidence_type=EvidenceType.HTTP_RESPONSE,
                    source="test",
                    observed_value={"status": 503},
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
                    title="Site unavailable",
                    observed_value={"status": 503},
                    expected_condition="target is technically retrievable",
                    evidence_ids=("EVD-1",),
                    status="OPEN",
                )
                persistence.findings.add(finding)
                result = execute_m10(
                    audit_id="AUD-1",
                    finding_ids=("FND-1",),
                    persistence=persistence,
                    workspace=workspace,
                )

            with RecommendationPersistence(workspace) as repository:
                group = repository.get_group(result.remediation_group_ids[0])
                recommendation = repository.get_recommendation(result.recommendation_ids[0])
                self.assertIsNotNone(group)
                self.assertIsNotNone(recommendation)
                assert group is not None and recommendation is not None
                self.assertEqual(group.priority_class, PriorityClass.P0)
                self.assertEqual(recommendation.remediation_group_id, group.group_id)
                self.assertEqual(recommendation.priority_class, PriorityClass.P0)


if __name__ == "__main__":
    unittest.main()

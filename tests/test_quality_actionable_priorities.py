from __future__ import annotations

from rasai.quality.analysis import FindingAssessment, QualityBundle
from rasai.quality.reporting import _actionable_findings


def _finding(finding_id: str, status: str, score: float) -> FindingAssessment:
    return FindingAssessment(
        finding_id=finding_id,
        rule_id="BR-GEO-001",
        severity="HIGH",
        status=status,
        url="https://example.test/",
        device="MOBILE",
        title=finding_id,
        evidence_confidence="HIGH",
        confidence_reasons=("TEST",),
        provenance="DETERMINISTIC_RULE",
        scope_count=1,
        effort="LOW",
        operational_priority=score,
        priority_class="P0" if score >= 80 else "P1",
    )


def test_actionable_priorities_exclude_inactive_findings_before_top_n() -> None:
    resolved = tuple(_finding(f"RES-{index}", "RESOLVED", 100 - index) for index in range(12))
    active_high = _finding("ACTIVE-HIGH", "OPEN", 79)
    active_low = _finding("ACTIVE-LOW", "OPEN", 61)
    bundle = QualityBundle(
        audit_id="AUD-Q",
        generated_at="2026-09-01T00:00:00+00:00",
        health_checks=(),
        finding_assessments=resolved + (active_low, active_high),
        coverage_map=(),
        recommendation_assessments=(),
        methodology={},
    )
    actionable = _actionable_findings(bundle)
    assert [item.finding_id for item in actionable] == ["ACTIVE-HIGH", "ACTIVE-LOW"]


def test_actionable_priorities_exclude_closed_and_dismissed_case_insensitively() -> None:
    bundle = QualityBundle(
        audit_id="AUD-Q",
        generated_at="2026-09-01T00:00:00+00:00",
        health_checks=(),
        finding_assessments=(
            _finding("CLOSED", "closed", 90),
            _finding("DISMISSED", "Dismissed", 89),
            _finding("OPEN", "OPEN", 50),
        ),
        coverage_map=(),
        recommendation_assessments=(),
        methodology={},
    )
    assert [item.finding_id for item in _actionable_findings(bundle)] == ["OPEN"]

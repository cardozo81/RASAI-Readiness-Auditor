"""Critical M9 scoring tests."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.scoring import ConsolidationStatus, SCORING_VERSION, ScoringEngine


_NOW = datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc)


def _execution(
    rule_id: str,
    result: RuleResult,
    *,
    page: str = "P1",
    device: DeviceContext | None = DeviceContext.DESKTOP,
    observed_value: dict[str, object] | None = None,
) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=f"REX-{rule_id}-{result.value}-{page}-{device.value if device else 'GLOBAL'}",
        audit_id="AUD-1", rule_id=rule_id, rule_version="1", page_id=page,
        snapshot_id=None, device=device, result=result,
        observed_value=observed_value or {}, expected_condition="fixture",
        evidence_ids=("EVD-1",), executed_at=_NOW,
    )


def _baseline_dimensions_without_structured_data() -> tuple[RuleExecution, ...]:
    """One fully evaluated representative scoring group for every non-Structured-Data dimension."""

    return (
        _execution("BR-GEO-005", RuleResult.PASS),
        _execution("BR-GEO-011", RuleResult.PASS),
        _execution("BR-GEO-025", RuleResult.PASS),
        _execution("BR-GEO-028", RuleResult.PASS),
        _execution("BR-GEO-031", RuleResult.PASS),
        _execution("BR-GEO-038", RuleResult.PASS),
        _execution("BR-GEO-041", RuleResult.PASS),
        _execution("BR-GEO-045", RuleResult.PASS),
        _execution("BR-GEO-048", RuleResult.PASS),
    )


class M9ScoringTests(unittest.TestCase):
    def test_unknown_reduces_coverage_without_reducing_quality_factor(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(
                _execution("BR-GEO-028", RuleResult.PASS),
                _execution("BR-GEO-029", RuleResult.UNKNOWN),
                _execution("BR-GEO-030", RuleResult.PASS),
            ),
        )
        score = next(item for item in result.scores if item.device is DeviceContext.DESKTOP and item.dimension == "SEMANTIC_STRUCTURE")
        self.assertEqual(score.value, 100.0)
        self.assertAlmostEqual(score.coverage, 2 / 3, places=6)
        self.assertEqual(score.consolidation_status, ConsolidationStatus.PARTIAL)

    def test_max_impact_collapses_correlated_fail_and_pass_once(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(
                _execution("BR-GEO-011", RuleResult.PASS),
                _execution("BR-GEO-012", RuleResult.FAIL),
                _execution("BR-GEO-015", RuleResult.PASS),
            ),
        )
        score = next(item for item in result.scores if item.device is DeviceContext.DESKTOP and item.dimension == "INDEXABILITY")
        contributions = [item for item in result.contributions if item.score_id == score.score_id]
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].result, RuleResult.FAIL)
        self.assertEqual(score.value, 0.0)

    def test_overall_remains_not_consolidated_when_required_dimensions_missing(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(_execution("BR-GEO-005", RuleResult.PASS),),
        )
        overall = result.overall_by_device[DeviceContext.DESKTOP]
        self.assertIsNone(overall.value)
        self.assertEqual(overall.consolidation_status, ConsolidationStatus.NOT_CONSOLIDATED)
        structured = next(
            item for item in result.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == "STRUCTURED_DATA"
        )
        self.assertEqual(structured.consolidation_status, ConsolidationStatus.NOT_CONSOLIDATED)
        self.assertIn("NO_RULE_EXECUTIONS", structured.limitations)

    def test_fully_not_applicable_dimension_is_excluded_without_penalty(self) -> None:
        structured_na = tuple(
            _execution(f"BR-GEO-{number:03d}", RuleResult.NOT_APPLICABLE)
            for number in range(34, 38)
        )
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(*_baseline_dimensions_without_structured_data(), *structured_na),
        )
        structured = next(
            item for item in result.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == "STRUCTURED_DATA"
        )
        overall = result.overall_by_device[DeviceContext.DESKTOP]

        self.assertIsNone(structured.value)
        self.assertEqual(structured.consolidation_status, ConsolidationStatus.NOT_APPLICABLE)
        self.assertIn("NO_APPLICABLE_RULES", structured.limitations)
        self.assertEqual(overall.value, 100.0)
        self.assertEqual(overall.coverage, 1.0)
        self.assertEqual(overall.consolidation_status, ConsolidationStatus.CONSOLIDATED)
        self.assertIn("DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA", overall.limitations)
        self.assertEqual(overall.scoring_version, "SCORE-GEO-002")
        self.assertEqual(SCORING_VERSION, "SCORE-GEO-002")

    def test_structured_data_when_present_enters_overall_calculation(self) -> None:
        structured = (
            _execution("BR-GEO-034", RuleResult.PASS, observed_value={"present": True, "blocks": 1}),
            _execution("BR-GEO-035", RuleResult.PASS, observed_value={"present": True, "types": ["Organization"]}),
            _execution("BR-GEO-036", RuleResult.PASS, observed_value={"structured_data_present": True}),
            _execution("BR-GEO-037", RuleResult.PASS, observed_value={"structured_data_present": True}),
        )
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(*_baseline_dimensions_without_structured_data(), *structured),
        )
        structured_score = next(
            item for item in result.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == "STRUCTURED_DATA"
        )
        overall = result.overall_by_device[DeviceContext.DESKTOP]

        self.assertEqual(structured_score.value, 100.0)
        self.assertEqual(structured_score.coverage, 1.0)
        self.assertEqual(structured_score.consolidation_status, ConsolidationStatus.CONSOLIDATED)
        self.assertEqual(overall.value, 100.0)
        self.assertNotIn("DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA", overall.limitations)

    def test_applicable_structured_data_failure_changes_overall_score(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(
                *_baseline_dimensions_without_structured_data(),
                _execution(
                    "BR-GEO-034",
                    RuleResult.FAIL,
                    observed_value={"present": True, "blocks": 1, "invalid_blocks": 1},
                ),
            ),
        )
        structured = next(
            item for item in result.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == "STRUCTURED_DATA"
        )
        overall = result.overall_by_device[DeviceContext.DESKTOP]

        self.assertEqual(structured.value, 0.0)
        self.assertEqual(structured.consolidation_status, ConsolidationStatus.CONSOLIDATED)
        self.assertEqual(overall.value, 90.0)

    def test_prerequisite_blocked_not_applicable_dimension_still_blocks_overall(self) -> None:
        blocked = tuple(
            _execution(
                f"BR-GEO-{number:03d}",
                RuleResult.NOT_APPLICABLE,
                observed_value={"reason": "SEMANTIC_PREREQUISITE_BLOCKED"},
            )
            for number in range(34, 38)
        )
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(*_baseline_dimensions_without_structured_data(), *blocked),
        )
        structured = next(
            item for item in result.scores
            if item.device is DeviceContext.DESKTOP and item.dimension == "STRUCTURED_DATA"
        )
        overall = result.overall_by_device[DeviceContext.DESKTOP]

        self.assertEqual(structured.consolidation_status, ConsolidationStatus.NOT_CONSOLIDATED)
        self.assertIn("APPLICABILITY_UNRESOLVED:PREREQUISITE_BLOCKED", structured.limitations)
        self.assertIsNone(overall.value)
        self.assertIn("DIMENSION_NOT_CONSOLIDATED:STRUCTURED_DATA", overall.limitations)

    def test_device_independent_execution_contributes_once_to_each_device(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-1",
            executions=(_execution("BR-GEO-005", RuleResult.PASS, device=None),),
        )
        desktop = next(item for item in result.scores if item.device is DeviceContext.DESKTOP and item.dimension == "TECHNICAL_ACCESSIBILITY")
        mobile = next(item for item in result.scores if item.device is DeviceContext.MOBILE and item.dimension == "TECHNICAL_ACCESSIBILITY")
        self.assertEqual(desktop.value, 100.0)
        self.assertEqual(mobile.value, 100.0)


if __name__ == "__main__":
    unittest.main()

"""M8 contract tests for configurable device scope."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import MagicMock, patch

from rasai.comparison import DeviceComparison, DeviceComparisonOutcome
from rasai.device_context import DEVICE_CONTEXT_ENV
from rasai.domain import DeviceContext, RuleResult
from rasai.m3 import M3ExecutionResult
from rasai.m8 import execute_m8


class _Repo:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = values or {}
        self.added: list[object] = []

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def add(self, value: object) -> None:
        self.added.append(value)


class _SemanticContext:
    def __enter__(self) -> "_SemanticContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def list_entities(self, snapshot_id: str):
        return ()

    def list_assessments(self, snapshot_id: str):
        return ()


class DeviceContextM8ContractTests(unittest.TestCase):
    def _execute(self, context: str):
        snapshot_ids: dict[DeviceContext, str]
        snapshots: dict[str, object]
        if context == "mobile":
            snapshot_ids = {DeviceContext.MOBILE: "SNP-M"}
            snapshots = {"SNP-M": object()}
        elif context == "desktop":
            snapshot_ids = {DeviceContext.DESKTOP: "SNP-D"}
            snapshots = {"SNP-D": object()}
        else:
            snapshot_ids = {
                DeviceContext.DESKTOP: "SNP-D",
                DeviceContext.MOBILE: "SNP-M",
            }
            snapshots = {"SNP-D": object(), "SNP-M": object()}

        persistence = SimpleNamespace(
            snapshots=_Repo(snapshots),
            rule_executions=_Repo(),
            findings=_Repo(),
        )
        evidence_manager = MagicMock()
        evidence_manager.record.return_value = SimpleNamespace(evidence_id="EV-1")
        comparison = DeviceComparison(
            outcome=DeviceComparisonOutcome.SAME,
            changed_fields=(),
            material_fields=(),
            desktop={},
            mobile={},
            limitations=(),
        )

        with patch.dict(os.environ, {DEVICE_CONTEXT_ENV: context}, clear=False):
            with patch("rasai.m8.EvidenceManager", return_value=evidence_manager):
                with patch("rasai.m8.SemanticPersistence", return_value=_SemanticContext()):
                    with patch("rasai.m8.DeviceComparator.compare", return_value=comparison) as compare:
                        result = execute_m8(
                            audit_id="AUD-1",
                            m3_result=M3ExecutionResult(
                                snapshot_ids={"PGE-1": snapshot_ids},
                                failures=(),
                            ),
                            persistence=persistence,
                            workspace=SimpleNamespace(root=Path(".")),
                        )
        return result, persistence, compare

    def test_mobile_only_marks_br_geo_052_not_applicable(self) -> None:
        result, persistence, compare = self._execute("mobile")
        compare.assert_not_called()
        self.assertEqual(result.outcomes_by_page["PGE-1"], DeviceComparisonOutcome.NOT_APPLICABLE)
        self.assertEqual(len(persistence.rule_executions.added), 1)
        execution = persistence.rule_executions.added[0]
        self.assertEqual(execution.result, RuleResult.NOT_APPLICABLE)
        self.assertEqual(execution.observed_value["reason_code"], "DEVICE_COMPARISON_DISABLED_BY_CONTEXT")
        self.assertEqual(execution.observed_value["selected_devices"], ["MOBILE"])
        self.assertFalse(execution.observed_value["comparison_requested"])
        self.assertEqual(persistence.findings.added, [])

    def test_desktop_only_marks_br_geo_052_not_applicable(self) -> None:
        result, persistence, compare = self._execute("desktop")
        compare.assert_not_called()
        self.assertEqual(result.outcomes_by_page["PGE-1"], DeviceComparisonOutcome.NOT_APPLICABLE)
        execution = persistence.rule_executions.added[0]
        self.assertEqual(execution.result, RuleResult.NOT_APPLICABLE)
        self.assertEqual(execution.observed_value["reason_code"], "DEVICE_COMPARISON_DISABLED_BY_CONTEXT")
        self.assertEqual(execution.observed_value["selected_devices"], ["DESKTOP"])
        self.assertFalse(execution.observed_value["comparison_requested"])

    def test_both_preserves_cross_device_comparison(self) -> None:
        result, persistence, compare = self._execute("both")
        compare.assert_called_once()
        self.assertEqual(result.outcomes_by_page["PGE-1"], DeviceComparisonOutcome.SAME)
        execution = persistence.rule_executions.added[0]
        self.assertEqual(execution.result, RuleResult.PASS)
        self.assertIsNone(execution.observed_value["reason_code"])
        self.assertEqual(execution.observed_value["selected_devices"], ["DESKTOP", "MOBILE"])
        self.assertTrue(execution.observed_value["comparison_requested"])


if __name__ == "__main__":
    unittest.main()

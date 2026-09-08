from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.m11 import _PersistedInputAwareReportBuilder
from rasai.m9 import _reproducibility_check
from rasai.scoring import ScoringEngine, ScoringResult


_NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class _ReopenedScoring:
    def __init__(self, original: ScoringResult) -> None:
        self._original = original

    def get_score(self, score_id: str):
        return next((score for score in (*self._original.scores, *self._original.overall_by_device.values()) if score.score_id == score_id), None)

    def list_contributions(self, score_id: str):
        return tuple(sorted(
            (item for item in self._original.contributions if item.score_id == score_id),
            key=lambda item: item.contribution_id,
        ))


class HotfixAIReportingIntegrityTests(unittest.TestCase):
    def test_br_geo_054_is_order_independent_after_sqlite_reopen(self) -> None:
        executions = (
            RuleExecution(
                rule_execution_id="REX-5",
                audit_id="AUD-HOTFIX",
                rule_id="BR-GEO-005",
                rule_version="1",
                page_id="PGE-1",
                snapshot_id="SNP-1",
                device=DeviceContext.DESKTOP,
                result=RuleResult.PASS,
                observed_value={"status": 200},
                expected_condition="page is recoverable",
                evidence_ids=("EV-5",),
                executed_at=_NOW,
            ),
            RuleExecution(
                rule_execution_id="REX-7",
                audit_id="AUD-HOTFIX",
                rule_id="BR-GEO-007",
                rule_version="1",
                page_id="PGE-1",
                snapshot_id="SNP-1",
                device=DeviceContext.DESKTOP,
                result=RuleResult.PASS,
                observed_value={"redirects": []},
                expected_condition="redirects are valid",
                evidence_ids=("EV-7",),
                executed_at=_NOW,
            ),
        )
        calculated = ScoringEngine().score(audit_id="AUD-HOTFIX", executions=executions)
        self.assertTrue(any(
            sum(item.score_id == score.score_id for item in calculated.contributions) >= 2
            for score in calculated.scores
        ))

        # SQLite reads contributions ordered by contribution_id. Force the
        # in-memory sequence into the opposite lexical order to reproduce the
        # former false FAIL without changing any contribution content.
        forced = tuple(
            replace(item, contribution_id=f"SCN-{9999 - index:04d}")
            for index, item in enumerate(calculated.contributions)
        )
        original = ScoringResult(
            scores=calculated.scores,
            contributions=forced,
            overall_by_device=calculated.overall_by_device,
        )

        result = _reproducibility_check(
            audit_id="AUD-HOTFIX",
            executions=executions,
            original=original,
            scoring=_ReopenedScoring(original),
        )

        self.assertTrue(result["contributions_reopenable"])
        self.assertTrue(result["reproducible"])

    def test_failed_openai_call_is_reported_as_configured_but_unavailable(self) -> None:
        audit = {
            "project_name": "Projeto",
            "audit_id": "AUD-AI",
            "started_at": _NOW.isoformat(),
            "created_at": _NOW.isoformat(),
            "capabilities": json.dumps(["filesystem", "sqlite", "semantic_provider:OPENAI"]),
            "limitations": json.dumps([
                "AI_PROVIDER_UNAVAILABLE:HTTP_429:type=insufficient_quota:code=credit_balance_exhausted:request_id=req_test"
            ]),
        }
        semantic = [
            {"provider": "DETERMINISTIC", "model": None},
            {"provider": "UNAVAILABLE", "model": None},
        ]
        builder = _PersistedInputAwareReportBuilder(None)  # type: ignore[arg-type]

        html = builder._executive(
            audit=audit,  # type: ignore[arg-type]
            domain="https://example.com",
            target_type="URL_SET",
            supplied_count=2,
            audited_count=2,
            semantic=semantic,  # type: ignore[arg-type]
        )

        self.assertIn("TENTATIVA SEM SUCESSO", html)
        self.assertIn("Provider configurado", html)
        self.assertIn("OPENAI - CHAMADA/RESPOSTA INDISPONÍVEL", html)
        self.assertIn("CONFIGURADO · NÃO CONFIRMADO POR RESPOSTA VÁLIDA", html)
        self.assertIn("HTTP_429", html)
        self.assertNotIn("<small>Modelo</small><strong>NÃO APLICÁVEL", html)


if __name__ == "__main__":
    unittest.main()

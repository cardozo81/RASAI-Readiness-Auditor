"""Regression coverage for SCORE-GEO-004 applicability and Structured Data flow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.domain import Audit, AuditMode, DeviceContext, RuleExecution, RuleResult, new_id
from rasai.m7 import execute_m7
from rasai.m11 import execute_m11
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.score_geo_004 import SCORING_VERSION
from rasai.scoring import ConsolidationStatus, ScoringEngine
from rasai.scoring_persistence import ScoringPersistence
from rasai.semantic import OpenAIProvider, SEMANTIC_RULE_IDS
from tests.test_m7_semantic_provider import _fixture


_NOW = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)


def _execution(rule_id: str, result: RuleResult, *, observed: dict[str, object] | None = None) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id="AUD-SCORE-004",
        rule_id=rule_id,
        rule_version="1",
        page_id="P1",
        snapshot_id=None,
        device=DeviceContext.DESKTOP,
        result=result,
        observed_value=observed or {},
        expected_condition="fixture",
        evidence_ids=("EVD-1",),
        executed_at=_NOW,
    )


def _baseline_without_structured_data() -> tuple[RuleExecution, ...]:
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


class ScoreGeo004ApplicabilityTests(unittest.TestCase):
    def test_real_m7_json_ld_fixture_enters_structured_data_and_overall_flow(self) -> None:
        captured_requests: list[dict[str, object]] = []

        def transport(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> dict[str, object]:
            request = json.loads(body.decode("utf-8"))
            captured_requests.append(request)
            text = request["input"][0]["content"][0]["text"]
            page_payload = json.loads(text.split("JSON page evidence:\n", 1)[1])
            evidence_id = page_payload["evidence"][0]["evidence_id"]
            payload = {
                "assessments": [
                    {
                        "rule_id": rule_id,
                        "result": "PASS",
                        "confidence": 0.95,
                        "evidence_ids": [evidence_id],
                        "reasoning_summary": f"validated {rule_id}",
                        "observed_value": {"summary": f"observation {rule_id}", "details": []},
                    }
                    for rule_id in SEMANTIC_RULE_IDS
                ],
                "entities": [],
                "primary_intent": "entender o Produto Alpha",
                "secondary_intents": ["preço"],
            }
            return {"output_text": json.dumps(payload, ensure_ascii=False)}

        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, m3, m4, m5, m6, _, _ = _fixture(workspace, persistence)
                result = execute_m7(
                    audit_id=audit.audit_id,
                    m3_result=m3,
                    m4_result=m4,
                    m5_result=m5,
                    m6_result=m6,
                    persistence=persistence,
                    workspace=workspace,
                    provider=OpenAIProvider(
                        model="semantic-test-model",
                        api_key="test-secret",
                        transport=transport,
                    ),
                )
                executions = [
                    persistence.rule_executions.get(execution_id)
                    for execution_id in result.rule_execution_ids
                ]
                semantic_executions = tuple(item for item in executions if item is not None)
                by_rule = {item.rule_id: item for item in semantic_executions}
                self.assertEqual(by_rule["BR-GEO-034"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-035"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-036"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-037"].result, RuleResult.PASS)
                self.assertEqual(len(captured_requests), 1)

                prior = tuple(
                    item
                    for execution_id in (*m5.rule_execution_ids, *m6.rule_execution_ids)
                    if (item := persistence.rule_executions.get(execution_id)) is not None
                )
                technical = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-005",
                    rule_version="1",
                    page_id=None,
                    snapshot_id=None,
                    device=None,
                    result=RuleResult.PASS,
                    observed_value={},
                    expected_condition="fixture",
                    evidence_ids=("EVD-TECH",),
                    executed_at=_NOW,
                )
                indexable = RuleExecution(
                    rule_execution_id=new_id("REX"),
                    audit_id=audit.audit_id,
                    rule_id="BR-GEO-011",
                    rule_version="1",
                    page_id=None,
                    snapshot_id=None,
                    device=None,
                    result=RuleResult.PASS,
                    observed_value={},
                    expected_condition="fixture",
                    evidence_ids=("EVD-IDX",),
                    executed_at=_NOW,
                )
                scoring = ScoringEngine().score(
                    audit_id=audit.audit_id,
                    executions=(*prior, technical, indexable, *semantic_executions),
                )
                structured = next(
                    score for score in scoring.scores
                    if score.device is DeviceContext.DESKTOP and score.dimension == "STRUCTURED_DATA"
                )
                overall = scoring.overall_by_device[DeviceContext.DESKTOP]
                self.assertEqual(structured.scoring_version, SCORING_VERSION)
                self.assertEqual(structured.value, 100.0)
                self.assertEqual(structured.consolidation_status, ConsolidationStatus.CONSOLIDATED)
                self.assertEqual(overall.value, 100.0)
                self.assertEqual(overall.consolidation_status, ConsolidationStatus.CONSOLIDATED)

    def test_report_calculates_score_when_structured_data_is_legitimately_not_applicable(self) -> None:
        scoring = ScoringEngine().score(
            audit_id="AUD-SCORE-004",
            executions=(
                *_baseline_without_structured_data(),
                *(
                    _execution(f"BR-GEO-{number:03d}", RuleResult.NOT_APPLICABLE)
                    for number in range(34, 38)
                ),
            ),
        )
        overall = scoring.overall_by_device[DeviceContext.DESKTOP]
        self.assertEqual(overall.scoring_version, "SCORE-GEO-004")
        self.assertEqual(overall.value, 100.0)
        self.assertEqual(overall.consolidation_status, ConsolidationStatus.CONSOLIDATED)
        self.assertIn("DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA", overall.limitations)

        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(Path(temp_dir), "AUD-SCORE-004")
            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(
                    Audit(
                        audit_id="AUD-SCORE-004",
                        project_name="Applicability report",
                        audit_mode=AuditMode.FULL,
                        auditor_version="0.1.0",
                        ruleset_version="RULESET-1",
                    )
                )
                with ScoringPersistence(workspace) as store:
                    for score in scoring.scores:
                        if score.device is DeviceContext.DESKTOP:
                            store.add_score(score)
                    store.add_score(overall)

                execute_m11(
                    audit_id="AUD-SCORE-004",
                    persistence=persistence,
                    workspace=workspace,
                )

            html = (workspace.root / "report.html").read_text(encoding="utf-8")
            self.assertIn("100.0", html)
            self.assertIn("Dados Estruturados", html)
            self.assertIn("NÃO APLICÁVEL", html)
            self.assertIn("Fora do universo aplicável", html)
            self.assertIn("Dimensões aplicáveis:</strong> 10 de 11", html)
            self.assertIn("A exclusão não atribui nota zero nem nota máxima", html)


if __name__ == "__main__":
    unittest.main()

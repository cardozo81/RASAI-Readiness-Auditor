"""Risk-oriented tests for M7 — Semantic Provider + Fallback."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from searchgeo.domain import (
    ArchitectureClassification,
    Audit,
    AuditMode,
    DeviceContext,
    DiscoverySource,
    Evidence,
    EvidenceType,
    Page,
    PageSnapshot,
    RuleExecution,
    RuleResult,
    new_id,
)
from searchgeo.m3 import M3ExecutionResult
from searchgeo.m4 import M4ExecutionResult
from searchgeo.m5 import M5ExecutionResult
from searchgeo.m6 import M6ExecutionResult
from searchgeo.m7 import execute_m7, m7_rule_ids
from searchgeo.persistence import AuditPersistence, AuditWorkspace
from searchgeo.semantic import NoneProvider, OpenAIProvider, SEMANTIC_RULE_IDS
from searchgeo.semantic_persistence import SemanticPersistence


_NOW = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)


def _fixture(
    workspace: AuditWorkspace,
    persistence: AuditPersistence,
    *,
    title: str | None = "Guia de Produto Alpha",
) -> tuple[Audit, M3ExecutionResult, M4ExecutionResult, M5ExecutionResult, M6ExecutionResult, str, str]:
    audit = Audit(audit_id=workspace.root.name, project_name="M7 semantic test")
    persistence.audits.add(audit)
    page = Page(
        page_id=new_id("PGE"),
        audit_id=audit.audit_id,
        normalized_url="https://example.test/produto",
        discovered_url="https://example.test/produto",
        discovery_sources=(DiscoverySource.SEED,),
    )
    persistence.pages.add(page)

    main = workspace.artifacts / "main.txt"
    main.write_text(
        "Produto Alpha da Marca Exemplo custa R$ 199,90. O guia explica recursos, uso e garantia.",
        encoding="utf-8",
    )
    structured = workspace.artifacts / "structured.json"
    structured.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "index": 0,
                        "raw": '{"@type":"Product"}',
                        "parsed": {"@context": "https://schema.org", "@type": "Product", "name": "Produto Alpha"},
                        "parse_error": None,
                        "types": ["Product"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot = PageSnapshot(
        snapshot_id=new_id("SNP"),
        page_id=page.page_id,
        device=DeviceContext.DESKTOP,
        requested_url=page.normalized_url,
        final_url=page.normalized_url,
        captured_at=_NOW,
        http_status=200,
        content_type="text/html",
        title=title,
        main_content_ref=main.relative_to(workspace.root).as_posix(),
        structured_data_ref=structured.relative_to(workspace.root).as_posix(),
        architecture_classification=ArchitectureClassification.STATIC_OR_SSR,
    )
    persistence.snapshots.add(snapshot)
    source_evidence = Evidence(
        evidence_id=new_id("EV-GEO"),
        audit_id=audit.audit_id,
        page_id=page.page_id,
        snapshot_id=snapshot.snapshot_id,
        device=DeviceContext.DESKTOP,
        evidence_type=EvidenceType.MAIN_CONTENT,
        source="m7-fixture",
        observed_value={"excerpt": "Produto Alpha da Marca Exemplo custa R$ 199,90."},
        artifact_reference=snapshot.main_content_ref,
        captured_at=_NOW,
    )
    persistence.evidence.add(source_evidence)

    br009 = RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id=audit.audit_id,
        rule_id="BR-GEO-009",
        rule_version="1",
        page_id=page.page_id,
        snapshot_id=None,
        device=None,
        result=RuleResult.PASS,
        observed_value={},
        expected_condition="fixture",
        evidence_ids=(),
        executed_at=_NOW,
    )
    persistence.rule_executions.add(br009)
    br020 = RuleExecution(
        rule_execution_id=new_id("REX"),
        audit_id=audit.audit_id,
        rule_id="BR-GEO-020",
        rule_version="1",
        page_id=page.page_id,
        snapshot_id=snapshot.snapshot_id,
        device=DeviceContext.DESKTOP,
        result=RuleResult.PASS,
        observed_value={},
        expected_condition="fixture",
        evidence_ids=(),
        executed_at=_NOW,
    )
    persistence.rule_executions.add(br020)

    m3 = M3ExecutionResult(
        snapshot_ids={page.page_id: {DeviceContext.DESKTOP: snapshot.snapshot_id}},
        failures=(),
    )
    m4 = M4ExecutionResult(
        evidence_ids={snapshot.snapshot_id: (source_evidence.evidence_id,)},
        failures=(),
    )
    m5 = M5ExecutionResult(
        rule_execution_ids=(br009.rule_execution_id,),
        finding_ids=(),
        registry_rule_ids=tuple(f"BR-GEO-{number:03d}" for number in range(1, 19)),
    )
    m6 = M6ExecutionResult(
        rule_execution_ids=(br020.rule_execution_id,),
        finding_ids=(),
        architecture_by_snapshot={snapshot.snapshot_id: ArchitectureClassification.STATIC_OR_SSR},
    )
    return audit, m3, m4, m5, m6, snapshot.snapshot_id, source_evidence.evidence_id


class M7SemanticProviderTests(unittest.TestCase):
    def test_no_ai_keeps_semantic_rules_unknown_but_deterministic_checks_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, m3, m4, m5, m6, snapshot_id, _ = _fixture(workspace, persistence, title=None)
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
                self.assertEqual(by_rule["BR-GEO-028"].result, RuleResult.FAIL)
                self.assertEqual(by_rule["BR-GEO-034"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-035"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-038"].result, RuleResult.UNKNOWN)
                self.assertIn("AI_DISABLED_BY_CONFIGURATION", persistence.audits.get(audit.audit_id).limitations)
                finding_rules = {
                    persistence.findings.get(item).rule_id
                    for item in result.finding_ids
                    if persistence.findings.get(item)
                }
                self.assertEqual(finding_rules, {"BR-GEO-028"})

            with SemanticPersistence(AuditWorkspace.open(workspace.root)) as semantic_store:
                assessments = semantic_store.list_assessments(snapshot_id)
                self.assertEqual(len(assessments), 22)
                self.assertEqual({item.assessment_type for item in assessments}, set(SEMANTIC_RULE_IDS))

    def test_openai_adapter_full_mode_validates_evidence_and_persists_semantic_entities(self) -> None:
        captured_requests: list[dict[str, object]] = []

        def transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict[str, object]:
            self.assertEqual(url, "https://api.openai.com/v1/responses")
            self.assertEqual(headers["Authorization"], "Bearer test-secret")
            self.assertGreater(timeout, 0)
            request = json.loads(body.decode("utf-8"))
            captured_requests.append(request)
            self.assertEqual(request["model"], "semantic-test-model")
            self.assertEqual(request["text"]["format"]["type"], "json_schema")
            text = request["input"][0]["content"][0]["text"]
            page_payload = json.loads(text.split("JSON page evidence:\n", 1)[1])
            evidence_id = page_payload["evidence"][0]["evidence_id"]
            assessments = []
            for rule_id in SEMANTIC_RULE_IDS:
                assessments.append(
                    {
                        "rule_id": rule_id,
                        "result": "WARNING" if rule_id == "BR-GEO-049" else "PASS",
                        "confidence": 0.9,
                        "evidence_ids": [evidence_id],
                        "reasoning_summary": f"validated {rule_id}",
                        "observed_value": {"summary": f"observation {rule_id}", "details": []},
                    }
                )
            payload = {
                "assessments": assessments,
                "entities": [
                    {
                        "name": "Produto Alpha",
                        "entity_type": "PRODUCT",
                        "confidence": 0.95,
                        "evidence_ids": [evidence_id],
                    }
                ],
                "primary_intent": "entender o Produto Alpha",
                "secondary_intents": ["preço", "garantia"],
            }
            return {"output_text": json.dumps(payload, ensure_ascii=False)}

        with TemporaryDirectory() as temp_dir:
            audit_id = new_id("AUD")
            workspace = AuditWorkspace.create(Path(temp_dir), audit_id)
            with AuditPersistence(workspace) as persistence:
                audit, m3, m4, m5, m6, snapshot_id, _ = _fixture(workspace, persistence)
                provider = OpenAIProvider(
                    model="semantic-test-model",
                    api_key="test-secret",
                    transport=transport,
                )
                result = execute_m7(
                    audit_id=audit.audit_id,
                    m3_result=m3,
                    m4_result=m4,
                    m5_result=m5,
                    m6_result=m6,
                    persistence=persistence,
                    workspace=workspace,
                    provider=provider,
                )
                self.assertEqual(result.audit_mode, AuditMode.FULL)
                self.assertEqual(m7_rule_ids(), SEMANTIC_RULE_IDS)
                self.assertEqual(len(captured_requests), 1)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                by_rule = {item.rule_id: item for item in executions if item}
                self.assertEqual(by_rule["BR-GEO-028"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-034"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-038"].result, RuleResult.PASS)
                self.assertEqual(by_rule["BR-GEO-049"].result, RuleResult.WARNING)
                self.assertEqual(by_rule["BR-GEO-048"].observed_value["primary_intent"], "entender o Produto Alpha")
                self.assertTrue(any(persistence.evidence.get(eid).evidence_type is EvidenceType.AI_ANALYSIS for eid in by_rule["BR-GEO-049"].evidence_ids))

            with SemanticPersistence(AuditWorkspace.open(workspace.root)) as semantic_store:
                entities = semantic_store.list_entities(snapshot_id)
                self.assertEqual(len(entities), 1)
                self.assertEqual(entities[0].name, "Produto Alpha")
                assessments = semantic_store.list_assessments(snapshot_id)
                self.assertEqual(len(assessments), 22)
                br049 = next(item for item in assessments if item.assessment_type == "BR-GEO-049")
                self.assertEqual(br049.result, RuleResult.WARNING)
                self.assertEqual(br049.provider, "OPENAI")
                self.assertEqual(br049.model, "semantic-test-model")

    def test_invalid_provider_evidence_degrades_without_penalizing_website(self) -> None:
        def transport(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> dict[str, object]:
            payload = {
                "assessments": [
                    {
                        "rule_id": "BR-GEO-038",
                        "result": "FAIL",
                        "confidence": 0.9,
                        "evidence_ids": ["EV-GEO-INVENTED"],
                        "reasoning_summary": "invented evidence",
                        "observed_value": {"summary": "invalid", "details": []},
                    }
                ],
                "entities": [],
                "primary_intent": None,
                "secondary_intents": [],
            }
            return {"output_text": json.dumps(payload)}

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
                    provider=OpenAIProvider(model="semantic-test-model", api_key="test-secret", transport=transport),
                )
                self.assertEqual(result.audit_mode, AuditMode.DEGRADED)
                executions = [persistence.rule_executions.get(item) for item in result.rule_execution_ids]
                by_rule = {item.rule_id: item for item in executions if item}
                self.assertEqual(by_rule["BR-GEO-038"].result, RuleResult.UNKNOWN)
                finding_rules = {
                    persistence.findings.get(item).rule_id
                    for item in result.finding_ids
                    if persistence.findings.get(item)
                }
                self.assertNotIn("BR-GEO-038", finding_rules)
                limitations = persistence.audits.get(audit.audit_id).limitations
                self.assertTrue(any(item.startswith("AI_PROVIDER_UNAVAILABLE") for item in limitations))


if __name__ == "__main__":
    unittest.main()

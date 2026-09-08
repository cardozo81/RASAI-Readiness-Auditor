from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.domain import (
    Audit,
    AuditTarget,
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
)
from rasai.m18_ai import OpenAIProvider
from rasai.m20 import execute_m20
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.semantic import NoneProvider

_NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class M20ContentRemediationTests(unittest.TestCase):
    def test_default_off_still_materializes_safe_jsonld_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory), structured=False)
            result = execute_m20(
                audit_id="AUD-M20",
                enabled=False,
                semantic_provider=NoneProvider(),
                workspace=workspace,
            )
            self.assertEqual(result.status, "DISABLED")
            self.assertEqual(result.suggestion_ids, ())
            self.assertEqual(len(result.jsonld_suggestion_ids), 1)

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                run = connection.execute("SELECT * FROM content_remediation_runs WHERE audit_id='AUD-M20'").fetchone()
                self.assertEqual(run["status"], "DISABLED")
                row = connection.execute("SELECT * FROM jsonld_remediation_suggestions WHERE audit_id='AUD-M20'").fetchone()
                self.assertEqual(row["status"], "MISSING_PROPOSED")
                proposed = json.loads(row["proposed_json"])
                self.assertEqual(proposed["@context"], "https://schema.org")
                self.assertEqual(proposed["@type"], "WebPage")
                self.assertEqual(proposed["url"], "https://example.test/servico")
                self.assertEqual(proposed["name"], "Serviço Exemplo")
                self.assertEqual(proposed["description"], "Descrição observada do serviço.")
                self.assertEqual(proposed["inLanguage"], "pt-BR")
            finally:
                connection.close()

    def test_enabled_ai_persists_exact_text_evidence_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory), structured=False)

            def transport(_url, _headers, body, _timeout):
                request = json.loads(body.decode("utf-8"))
                self.assertIn("people-first", request["instructions"])
                return {
                    "output_text": json.dumps({
                        "suggestions": [{
                            "finding_id": "FND-M20",
                            "objective": "Tornar a explicação mais direta.",
                            "target_location": "Após o H1 da página.",
                            "proposed_text": "O Serviço Exemplo apresenta uma explicação clara sobre a cobertura observada.",
                            "evidence_ids": ["EV-M20"],
                            "confidence": 0.9,
                            "review_note": "Confirmar terminologia com o responsável pelo conteúdo antes de publicar.",
                        }]
                    }),
                    "usage": {
                        "input_tokens": 100,
                        "input_tokens_details": {"cached_tokens": 10},
                        "output_tokens": 40,
                        "output_tokens_details": {"reasoning_tokens": 5},
                        "total_tokens": 140,
                    },
                }

            provider = OpenAIProvider(api_key="test", transport=transport)
            result = execute_m20(
                audit_id="AUD-M20",
                enabled=True,
                semantic_provider=provider,
                workspace=workspace,
            )
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(len(result.suggestion_ids), 1)
            self.assertEqual(result.attempted_contexts, 1)

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                suggestion = connection.execute("SELECT * FROM content_remediation_suggestions").fetchone()
                self.assertEqual(suggestion["finding_id"], "FND-M20")
                self.assertEqual(suggestion["provider"], "OPENAI")
                self.assertEqual(json.loads(suggestion["evidence_ids"]), ["EV-M20"])
                self.assertIn("Serviço Exemplo", suggestion["proposed_text"])
                attempt = connection.execute("SELECT * FROM content_remediation_attempts").fetchone()
                self.assertEqual(attempt["status"], "SUCCESS")
                self.assertEqual(attempt["input_tokens"], 100)
                self.assertEqual(attempt["output_tokens"], 40)
                self.assertEqual(attempt["contract_version"], "M20-CONTENT-REMEDIATION-v3")
            finally:
                connection.close()

    def test_unsupported_numeric_claim_is_rejected_as_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory), structured=False)

            def transport(_url, _headers, _body, _timeout):
                return {
                    "output_text": json.dumps({
                        "suggestions": [{
                            "finding_id": "FND-M20",
                            "objective": "Adicionar prova quantitativa.",
                            "target_location": "Após o H1.",
                            "proposed_text": "O serviço resolve 99% dos casos.",
                            "evidence_ids": ["EV-M20"],
                            "confidence": 0.9,
                            "review_note": "Revisar.",
                        }]
                    })
                }

            provider = OpenAIProvider(api_key="test", transport=transport)
            result = execute_m20(
                audit_id="AUD-M20",
                enabled=True,
                semantic_provider=provider,
                workspace=workspace,
            )
            self.assertEqual(result.status, "DEGRADED")
            self.assertEqual(result.suggestion_ids, ())
            connection = sqlite3.connect(workspace.database)
            try:
                status = connection.execute("SELECT status FROM content_remediation_attempts").fetchone()[0]
                self.assertEqual(status, "CONTRACT_ERROR")
            finally:
                connection.close()

    def test_existing_jsonld_is_reviewed_without_destructive_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._fixture(Path(directory), structured=True)
            result = execute_m20(
                audit_id="AUD-M20",
                enabled=False,
                semantic_provider=NoneProvider(),
                workspace=workspace,
            )
            self.assertEqual(len(result.jsonld_suggestion_ids), 1)
            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute("SELECT * FROM jsonld_remediation_suggestions").fetchone()
                self.assertEqual(row["status"], "EXISTING_REVIEW")
                self.assertIsNone(row["proposed_json"])
                self.assertEqual(json.loads(row["existing_types"]), ["WebPage"])
                improvements = json.loads(row["improvements"])
                self.assertTrue(any("url" in item for item in improvements))
                self.assertTrue(any("description" in item for item in improvements))
            finally:
                connection.close()

    @staticmethod
    def _fixture(root: Path, *, structured: bool) -> AuditWorkspace:
        workspace = AuditWorkspace.create(root, "AUD-M20")
        main_ref = "artifacts/main.txt"
        (workspace.root / main_ref).write_text(
            "Serviço Exemplo apresenta uma explicação clara sobre a cobertura observada.",
            encoding="utf-8",
        )
        structured_ref = None
        if structured:
            structured_ref = "artifacts/structured.json"
            payload = {
                "blocks": [{
                    "index": 0,
                    "raw": '{"@context":"https://schema.org","@type":"WebPage","name":"Serviço Exemplo"}',
                    "parsed": {
                        "@context": "https://schema.org",
                        "@type": "WebPage",
                        "name": "Serviço Exemplo",
                    },
                    "parse_error": None,
                    "types": ["WebPage"],
                }]
            }
            (workspace.root / structured_ref).write_text(json.dumps(payload), encoding="utf-8")

        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(
                audit_id="AUD-M20",
                project_name="M20",
                primary_language="pt-BR",
                auditor_version="test",
                ruleset_version="1",
            ))
            persistence.targets.add(AuditTarget(
                "TGT-M20",
                "AUD-M20",
                "https://example.test/servico",
                "https://example.test",
                TargetType.URL,
            ))
            persistence.pages.add(Page(
                "PGE-M20",
                "AUD-M20",
                "https://example.test/servico",
                "https://example.test/servico",
                (DiscoverySource.SEED,),
                0,
            ))
            persistence.snapshots.add(PageSnapshot(
                snapshot_id="SNP-M20",
                page_id="PGE-M20",
                device=DeviceContext.MOBILE,
                requested_url="https://example.test/servico",
                final_url="https://example.test/servico",
                captured_at=_NOW,
                http_status=200,
                title="Serviço Exemplo",
                description="Descrição observada do serviço.",
                canonical="https://example.test/servico",
                main_content_ref=main_ref,
                structured_data_ref=structured_ref,
            ))
            persistence.evidence.add(Evidence(
                evidence_id="EV-M20",
                audit_id="AUD-M20",
                page_id="PGE-M20",
                snapshot_id="SNP-M20",
                device=DeviceContext.MOBILE,
                evidence_type=EvidenceType.MAIN_CONTENT,
                source="fixture",
                observed_value={"excerpt": "Serviço Exemplo apresenta uma explicação clara sobre a cobertura observada."},
                artifact_reference=main_ref,
                captured_at=_NOW,
            ))
            persistence.rule_executions.add(RuleExecution(
                rule_execution_id="REX-M20",
                audit_id="AUD-M20",
                rule_id="BR-GEO-038",
                rule_version="1",
                page_id="PGE-M20",
                snapshot_id="SNP-M20",
                device=DeviceContext.MOBILE,
                result=RuleResult.WARNING,
                observed_value={"reason": "clarity gap"},
                expected_condition="content answers the relevant user question clearly",
                evidence_ids=("EV-M20",),
                executed_at=_NOW,
            ))
            persistence.findings.add(Finding(
                finding_id="FND-M20",
                audit_id="AUD-M20",
                rule_id="BR-GEO-038",
                rule_execution_id="REX-M20",
                page_id="PGE-M20",
                device=FindingDevice.MOBILE,
                category="ANSWERABILITY",
                severity=Severity.MEDIUM,
                source="fixture",
                title="Resposta pode ser mais explícita",
                observed_value={"reason": "clarity gap"},
                expected_condition="content answers the relevant user question clearly",
                evidence_ids=("EV-M20",),
                status="OPEN",
            ))
        return workspace


if __name__ == "__main__":
    unittest.main()

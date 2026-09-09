from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from rasai.search_intelligence.cli import build_parser
from rasai.search_intelligence.competitive import CompetitiveSelection
from rasai.search_intelligence.competitive_ai import (
    CompetitiveAiEvidenceError,
    CompetitiveAiState,
    FixtureCompetitiveAiProvider,
    OpenAICompetitiveAiProvider,
    build_competitive_ai_input,
    normalize_competitive_ai_payload,
)
from rasai.search_intelligence.competitive_ai_persistence import (
    CompetitiveAiRepository,
    FilesystemCompetitiveAiEvidenceSink,
)
from rasai.search_intelligence.competitive_ai_runtime import execute_competitive_ai
from rasai.search_intelligence.competitive_runtime import CompetitiveExecution
from rasai.search_intelligence.content import (
    CompetitiveContentAnalysis,
    CompetitiveGap,
    CompetitivePageFeatures,
    ContentFetchStatus,
)
from rasai.search_intelligence.models import (
    DomainMatchStatus,
    QueryOrigin,
    SearchIntelligenceResult,
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
)
from rasai.search_intelligence.runtime import SearchExecution


def _page(role: str, domain: str, url: str, *, words: int, body_terms: tuple[str, ...]):
    return CompetitivePageFeatures(
        role=role,
        domain=domain,
        requested_url=url,
        final_url=url,
        status=ContentFetchStatus.OBSERVED,
        http_status=200,
        content_type="text/html",
        content_sha256=("a" if role == "CUSTOMER" else "b") * 64,
        bytes_read=1000,
        title=f"{domain} seguro auto",
        meta_description="seguro auto",
        headings=("Seguro auto", "Coberturas"),
        word_count=words,
        query_terms=("seguro", "auto"),
        query_terms_in_title=("seguro", "auto"),
        query_terms_in_description=("seguro", "auto"),
        query_terms_in_headings=("seguro", "auto"),
        query_terms_in_body=body_terms,
        jsonld_types=("Product",),
    )


def _analysis(status: str = "CONSOLIDATED") -> CompetitiveContentAnalysis:
    customer_result = SerpResult(3, "cliente.com.br", "https://cliente.com.br/seguro")
    selection = CompetitiveSelection(
        query="seguro auto",
        customer_domain="cliente.com.br",
        customer_result=customer_result,
        classified_results=(),
        selected_candidates=(),
    )
    return CompetitiveContentAnalysis(
        selection=selection,
        customer_page=_page(
            "CUSTOMER",
            "cliente.com.br",
            "https://cliente.com.br/seguro",
            words=500,
            body_terms=("seguro",),
        ),
        competitor_pages=(
            _page(
                "COMPETITOR_CANDIDATE",
                "lider.com.br",
                "https://lider.com.br/seguro",
                words=900,
                body_terms=("seguro", "auto"),
            ),
        ),
        gaps=(
            CompetitiveGap(
                code="QUERY_BODY_COVERAGE_BELOW_LEADERS",
                severity="INFO",
                message="Cobertura da query abaixo da referência observada.",
                customer_value=0.5,
                leader_reference=1.0,
                evidence_urls=("https://lider.com.br/seguro",),
            ),
        ),
        comparison_status=status,
    )


def _payload(evidence_id: str = "CE-GAP-001") -> dict:
    return {
        "query_intent": "Comparar e contratar seguro automotivo.",
        "ymyl_assessment": "AUTO: potencial impacto financeiro; revisar com cautela.",
        "summary": "Há oportunidade de ampliar a cobertura informacional.",
        "opportunities": [
            {
                "category": "TOPIC_COVERAGE",
                "priority": "HIGH",
                "title": "Ampliar cobertura útil",
                "recommendation": "Explicar coberturas, exclusões e critérios relevantes.",
                "rationale": "A diferença determinística mostra menor cobertura da query.",
                "evidence_ids": [evidence_id],
                "confidence": 0.88,
                "causality_note": "Correlação observada; não comprova causa de ranking.",
            }
        ],
    }


def _observation() -> SerpObservation:
    return SerpObservation(
        observation_id="OBS-1",
        run_id="RUN-1",
        query="seguro auto",
        query_origin=QueryOrigin.MANUAL,
        engine="google",
        country="BR",
        region=None,
        language="pt-BR",
        device="desktop",
        collected_at=datetime.now(timezone.utc),
        provider="fixture",
        provider_request_id=None,
        requested_depth=10,
        result_count=1,
        results=(SerpResult(3, "cliente.com.br", "https://cliente.com.br/seguro"),),
        data_mode=SerpDataMode.FIXTURE,
        status=SerpObservationStatus.OBSERVED,
    )


class CompetitiveAiContractTests(unittest.TestCase):
    def test_input_uses_only_extracted_evidence(self) -> None:
        item = build_competitive_ai_input(
            "OBS-1",
            _analysis(),
            market="BR",
            language="pt-BR",
            ymyl_mode="AUTO",
            artifact_reference="artifacts/search-intelligence/competitive/OBS-1.json",
        )
        self.assertEqual(
            item.allowed_evidence_ids,
            frozenset({"CE-QUERY", "CE-CUSTOMER", "CE-COMP-001", "CE-GAP-001"}),
        )
        encoded = json.dumps(item.provider_payload())
        self.assertNotIn("<html", encoded.casefold())
        self.assertIn("content_sha256", encoded)

    def test_unknown_evidence_id_is_rejected(self) -> None:
        with self.assertRaises(CompetitiveAiEvidenceError):
            normalize_competitive_ai_payload(
                _payload("CE-UNKNOWN"),
                allowed_evidence_ids=frozenset({"CE-QUERY", "CE-GAP-001"}),
                provider="FIXTURE",
                model=None,
            )

    def test_fixture_provider_is_network_free_and_normalized(self) -> None:
        item = build_competitive_ai_input(
            "OBS-1",
            _analysis(),
            market="BR",
            language="pt-BR",
        )
        result = FixtureCompetitiveAiProvider(_payload()).analyze(item)
        self.assertEqual(result.state, CompetitiveAiState.AVAILABLE)
        self.assertIsNotNone(result.assessment)
        self.assertEqual(result.assessment.opportunities[0].evidence_ids, ("CE-GAP-001",))

    def test_openai_adapter_uses_strict_schema_and_does_not_put_key_in_body(self) -> None:
        captured = {}

        def transport(endpoint, headers, body, timeout):
            captured["endpoint"] = endpoint
            captured["headers"] = headers
            captured["body"] = body
            captured["timeout"] = timeout
            return {"id": "resp_1", "output_text": json.dumps(_payload())}

        item = build_competitive_ai_input(
            "OBS-1",
            _analysis(),
            market="BR",
            language="pt-BR",
        )
        provider = OpenAICompetitiveAiProvider(
            model="gpt-5.6-terra",
            api_key="secret-test-key",
            reasoning_effort="high",
            transport=transport,
        )
        result = provider.analyze(item)
        self.assertEqual(result.state, CompetitiveAiState.AVAILABLE)
        request_payload = json.loads(captured["body"].decode("utf-8"))
        self.assertTrue(request_payload["text"]["format"]["strict"])
        self.assertEqual(
            request_payload["text"]["format"]["schema"]["additionalProperties"],
            False,
        )
        self.assertNotIn("secret-test-key", captured["body"].decode("utf-8"))
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-test-key")


class CompetitiveAiRuntimeTests(unittest.TestCase):
    def _search_execution(self) -> SearchExecution:
        request = SerpQueryRequest(
            query="seguro auto",
            domain_of_interest="cliente.com.br",
            depth=10,
        )
        search_result = SearchIntelligenceResult(
            request=request,
            observation=_observation(),
            domain_status=DomainMatchStatus.FOUND,
            customer_position=3,
        )
        return SearchExecution(
            mode="fixture",
            provider="fixture",
            results=(search_result,),
            projected_http_request_ceiling=0,
            actual_http_requests=0,
            persisted=False,
        )

    def test_non_consolidated_content_never_calls_ai(self) -> None:
        class Provider:
            name = "TEST"

            def __init__(self):
                self.calls = 0

            def analyze(self, competitive_input):
                self.calls += 1
                return FixtureCompetitiveAiProvider(_payload()).analyze(competitive_input)

        provider = Provider()
        competitive = CompetitiveExecution(
            analyses=(_analysis("NO_OBSERVED_COMPETITOR_PAGES"),),
            content_enabled=True,
            content_http_requests=0,
            persisted=False,
        )
        execution = execute_competitive_ai(
            self._search_execution(),
            competitive,
            provider=provider,
            market="BR",
            language="pt-BR",
        )
        self.assertEqual(provider.calls, 0)
        self.assertEqual(execution.results[0].state, CompetitiveAiState.NOT_ELIGIBLE)

    def test_consolidated_content_calls_fixture_and_returns_assessment(self) -> None:
        competitive = CompetitiveExecution(
            analyses=(_analysis(),),
            content_enabled=True,
            content_http_requests=0,
            persisted=False,
        )
        execution = execute_competitive_ai(
            self._search_execution(),
            competitive,
            provider=FixtureCompetitiveAiProvider(_payload()),
            market="BR",
            language="pt-BR",
        )
        self.assertEqual(execution.eligible_analyses, 1)
        self.assertEqual(execution.provider_calls, 0)
        self.assertEqual(execution.results[0].state, CompetitiveAiState.AVAILABLE)


class CompetitiveAiPersistenceTests(unittest.TestCase):
    def test_additive_table_and_artifact(self) -> None:
        item = build_competitive_ai_input(
            "OBS-1",
            _analysis(),
            market="BR",
            language="pt-BR",
        )
        result = FixtureCompetitiveAiProvider(_payload()).analyze(item)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "audit.db"
            connection = sqlite3.connect(database)
            try:
                connection.executescript(
                    """
                    CREATE TABLE audits (
                        audit_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE serp_observations (
                        observation_id TEXT PRIMARY KEY
                    );
                    INSERT INTO audits VALUES ('AUD-1','2026-09-09T00:00:00Z');
                    INSERT INTO serp_observations VALUES ('OBS-1');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            repository = CompetitiveAiRepository.from_workspace(root)
            sink = FilesystemCompetitiveAiEvidenceSink(root)
            try:
                evidence_ref, evidence_sha = sink.write("OBS-1", result)
                repository.save(
                    "OBS-1",
                    result,
                    evidence_ref=evidence_ref,
                    evidence_sha256=evidence_sha,
                )
                row = repository.connection.execute(
                    "SELECT state,provider,opportunity_count,evidence_ref "
                    "FROM serp_competitive_ai_analyses WHERE observation_id='OBS-1'"
                ).fetchone()
            finally:
                repository.close()

            self.assertEqual(tuple(row[:3]), ("AVAILABLE", "FIXTURE", 1))
            self.assertTrue(row["evidence_ref"].endswith("competitive-ai/OBS-1.json"))
            self.assertTrue((root / row["evidence_ref"]).is_file())


class CompetitiveAiCliTests(unittest.TestCase):
    def test_cli_exposes_explicit_ai_controls(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "seguro auto",
                "--domain",
                "cliente.com.br",
                "--compare-content",
                "--ai-competitive",
                "--ai-provider",
                "fixture",
                "--ai-fixture",
                "answer.json",
                "--ymyl-mode",
                "ON",
            ]
        )
        self.assertTrue(args.ai_competitive)
        self.assertEqual(args.ai_provider, "fixture")
        self.assertEqual(args.ymyl_mode, "ON")


if __name__ == "__main__":
    unittest.main()

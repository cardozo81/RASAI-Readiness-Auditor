from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.report_contract import surface_by_id
from rasai.search_intelligence.reporting import write_search_intelligence_report


class SearchIntelligenceReportingTests(unittest.TestCase):
    def test_report_projects_serp_competitive_and_ai_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._database(root / "audit.db", include_observation=True, include_ai=True)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text(
                "<html><body><aside><nav><a href='index.html'>Visão</a></nav></aside>"
                "<main><header><h1>Auditoria</h1></header></main></body></html>",
                encoding="utf-8",
            )

            path = write_search_intelligence_report(root)
            self.assertIsNotNone(path)
            assert path is not None
            html = path.read_text(encoding="utf-8")

            self.assertIn("SERP Observation e Competitive Search Intelligence", html)
            self.assertIn("Provider de Search configurado", html)
            self.assertIn("serp_observations", html)
            self.assertIn("serp_results", html)
            self.assertIn("serp_competitive_results", html)
            self.assertIn("DETERMINISTIC-CORRELATIONAL-001", html)
            self.assertIn("seguro auto online", html)
            self.assertIn("serpapi", html)
            self.assertIn("FOUND", html)
            self.assertIn("#", html)
            self.assertIn("ORGANIC_CANDIDATE", html)
            self.assertIn("QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS", html)
            self.assertIn("COMPETITOR_CANDIDATE", html)
            self.assertIn("Article", html)
            self.assertIn("content-hash-competitor", html)

            # Forward-compatible projection of the parallel evidence-bound AI layer.
            self.assertIn("serp_competitive_ai_analyses", html)
            self.assertIn("OPENAI", html)
            self.assertIn("gpt-test", html)
            self.assertIn("COMPETITIVE-AI-001", html)
            self.assertIn("Informational / transactional", html)
            self.assertIn("TOPIC_COVERAGE", html)
            self.assertIn("CE-CUSTOMER", html)
            self.assertIn("não altera SARI-001", html)
            self.assertIn("SCORE-GEO-004", html)
            self.assertIn("correlação", html.casefold())

            # Canonical navigation and executive summary are idempotent.
            index = (report / "index.html").read_text(encoding="utf-8")
            self.assertIn("Search Intelligence", index)
            self.assertIn("search-intelligence.html", index)
            self.assertEqual(index.count("search-intelligence-summary"), 1)

            write_search_intelligence_report(root)
            index_again = (report / "index.html").read_text(encoding="utf-8")
            self.assertEqual(index_again.count("search-intelligence-summary"), 1)

            surface = surface_by_id("search-intelligence")
            self.assertEqual(surface.filename, "search-intelligence.html")
            self.assertTrue(surface.optional)
            self.assertIn("Nenhum impacto automático", surface.score_impact)

    def test_report_is_absent_without_persisted_serp_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._database(root / "audit.db", include_observation=False, include_ai=False)
            result = write_search_intelligence_report(root)
            self.assertIsNone(result)
            self.assertFalse((root / "report" / "search-intelligence.html").exists())

    @staticmethod
    def _database(path: Path, *, include_observation: bool, include_ai: bool) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                """
                CREATE TABLE serp_observations (
                    observation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    query_origin TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    country TEXT NOT NULL,
                    region TEXT,
                    language TEXT NOT NULL,
                    device TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_request_id TEXT,
                    requested_depth INTEGER NOT NULL,
                    result_count INTEGER NOT NULL,
                    data_mode TEXT NOT NULL,
                    observation_status TEXT NOT NULL,
                    domain_of_interest TEXT,
                    customer_position INTEGER,
                    domain_status TEXT NOT NULL,
                    raw_evidence_ref TEXT,
                    raw_evidence_sha256 TEXT,
                    config_metadata TEXT NOT NULL,
                    quality_metadata TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT
                );
                CREATE TABLE serp_results (
                    observation_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    snippet TEXT,
                    result_type TEXT NOT NULL,
                    serp_features TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE TABLE serp_competitive_analyses (
                    observation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    methodology TEXT NOT NULL,
                    comparison_status TEXT NOT NULL,
                    customer_url TEXT,
                    candidate_count INTEGER NOT NULL,
                    observed_competitor_pages INTEGER NOT NULL,
                    gap_count INTEGER NOT NULL,
                    gaps_json TEXT NOT NULL,
                    evidence_ref TEXT,
                    evidence_sha256 TEXT
                );
                CREATE TABLE serp_competitive_results (
                    observation_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    eligible_for_content_comparison INTEGER NOT NULL,
                    selected_for_content_comparison INTEGER NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE serp_competitive_pages (
                    observation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    requested_url TEXT NOT NULL,
                    final_url TEXT,
                    fetch_status TEXT NOT NULL,
                    http_status INTEGER,
                    content_type TEXT,
                    content_sha256 TEXT,
                    bytes_read INTEGER NOT NULL,
                    title TEXT,
                    meta_description TEXT,
                    headings_json TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    query_terms_json TEXT NOT NULL,
                    query_terms_title_json TEXT NOT NULL,
                    query_terms_description_json TEXT NOT NULL,
                    query_terms_headings_json TEXT NOT NULL,
                    query_terms_body_json TEXT NOT NULL,
                    jsonld_types_json TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    redirects_json TEXT NOT NULL
                );
                """
            )
            if include_ai:
                connection.executescript(
                    """
                    CREATE TABLE serp_competitive_ai_analyses (
                        observation_id TEXT PRIMARY KEY,
                        audit_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        reason TEXT,
                        provider TEXT,
                        model TEXT,
                        contract_version TEXT,
                        prompt_id TEXT,
                        prompt_version TEXT,
                        provider_request_id TEXT,
                        query_intent TEXT,
                        ymyl_assessment TEXT,
                        summary TEXT,
                        opportunity_count INTEGER NOT NULL,
                        opportunities_json TEXT NOT NULL,
                        evidence_ref TEXT,
                        evidence_sha256 TEXT
                    );
                    """
                )
            if not include_observation:
                connection.commit()
                return

            observation_id = "SERP-OBS-REPORT"
            connection.execute(
                """
                INSERT INTO serp_observations VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    observation_id,
                    "AUD-REPORT",
                    "SERP-RUN-REPORT",
                    "seguro auto online",
                    "MANUAL",
                    "google",
                    "BR",
                    "RS",
                    "pt-BR",
                    "desktop",
                    "2026-09-09T04:00:00+00:00",
                    "serpapi",
                    "provider-request-1",
                    20,
                    3,
                    "OBSERVED_API",
                    "OBSERVED",
                    "cliente.example",
                    3,
                    "FOUND",
                    "artifacts/search-intelligence/raw.json",
                    "raw-hash",
                    '{"surface":"test"}',
                    '{"pages_collected":1,"pages_requested_ceiling":1}',
                    None,
                    None,
                ),
            )
            connection.executemany(
                "INSERT INTO serp_results VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    (
                        observation_id,
                        1,
                        "leader.example",
                        "https://leader.example/auto",
                        "Seguro Auto Líder",
                        "Conteúdo observado",
                        "organic",
                        '["snippet"]',
                        "{}",
                    ),
                    (
                        observation_id,
                        3,
                        "cliente.example",
                        "https://cliente.example/auto",
                        "Seguro Auto Cliente",
                        "Página do cliente",
                        "organic",
                        "[]",
                        "{}",
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO serp_competitive_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    observation_id,
                    "AUD-REPORT",
                    "DETERMINISTIC-CORRELATIONAL-001",
                    "CONSOLIDATED",
                    "https://cliente.example/auto",
                    1,
                    1,
                    1,
                    '[{"code":"QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS","severity":"INFO","message":"Cobertura lexical menor.","customer_value":0.5,"leader_reference":1.0,"evidence_urls":["https://leader.example/auto"]}]',
                    "artifacts/search-intelligence/competitive/SERP-OBS-REPORT.json",
                    "competitive-hash",
                ),
            )
            connection.execute(
                "INSERT INTO serp_competitive_results VALUES (?,?,?,?,?,?,?,?)",
                (
                    observation_id,
                    1,
                    "leader.example",
                    "https://leader.example/auto",
                    "ORGANIC_CANDIDATE",
                    1,
                    1,
                    "external organic result; business equivalence is not inferred",
                ),
            )
            connection.executemany(
                "INSERT INTO serp_competitive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        observation_id,
                        "CUSTOMER",
                        "cliente.example",
                        "https://cliente.example/auto",
                        "https://cliente.example/auto",
                        "OBSERVED",
                        200,
                        "text/html",
                        "content-hash-customer",
                        1000,
                        "Seguro Auto Cliente",
                        "Seguro para seu carro",
                        '["Seguro Auto"]',
                        400,
                        '["seguro","auto","online"]',
                        '["seguro","auto"]',
                        '["seguro"]',
                        '["seguro","auto"]',
                        '["seguro","auto"]',
                        '["Product"]',
                        None,
                        None,
                        "[]",
                    ),
                    (
                        observation_id,
                        "COMPETITOR_CANDIDATE",
                        "leader.example",
                        "https://leader.example/auto",
                        "https://leader.example/auto",
                        "OBSERVED",
                        200,
                        "text/html",
                        "content-hash-competitor",
                        2000,
                        "Seguro Auto Líder",
                        "Seguro auto online completo",
                        '["Seguro Auto Online","Coberturas"]',
                        800,
                        '["seguro","auto","online"]',
                        '["seguro","auto","online"]',
                        '["seguro","auto"]',
                        '["seguro","auto","online"]',
                        '["seguro","auto","online"]',
                        '["Article","Product"]',
                        None,
                        None,
                        "[]",
                    ),
                ),
            )
            if include_ai:
                connection.execute(
                    "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        observation_id,
                        "AUD-REPORT",
                        "AVAILABLE",
                        None,
                        "OPENAI",
                        "gpt-test",
                        "COMPETITIVE-AI-001",
                        "rasai-competitive-search",
                        "1",
                        "ai-request-1",
                        "Informational / transactional",
                        "Not YMYL for fixture",
                        "A página líder cobre tópico adicional observado.",
                        1,
                        '[{"category":"TOPIC_COVERAGE","priority":"HIGH","title":"Cobrir tópico observado","recommendation":"Adicionar cobertura quando relevante ao produto.","rationale":"Diferença semântica apoiada pelas evidências.","evidence_ids":["CE-CUSTOMER","CE-COMP-001"],"confidence":0.82,"causality_note":"Hipótese não causal."}]',
                        "artifacts/search-intelligence/competitive-ai/SERP-OBS-REPORT.json",
                        "ai-hash",
                    ),
                )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

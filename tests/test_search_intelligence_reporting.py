from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.report_contract import surface_by_id
from rasai.search_intelligence.reporting import write_search_intelligence_report
from rasai.search_intelligence.runtime import _refresh_search_intelligence_report


class SearchIntelligenceReportingTests(unittest.TestCase):
    def test_report_projects_serp_competitive_and_ai_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root / "audit.db")
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text(
                "<html><body><aside><nav><a href='index.html'>Visão</a></nav></aside>"
                "<main><header><h1>Auditoria</h1></header></main></body></html>",
                encoding="utf-8",
            )

            # Runtime registration is intentionally forward-compatible with the
            # Competitive AI persistence contract evolving in a parallel branch.
            _refresh_search_intelligence_report(root)
            path = report / "search-intelligence.html"
            self.assertTrue(path.is_file())
            html = path.read_text(encoding="utf-8")

            for expected in (
                "SERP Observation e Competitive Search Intelligence",
                "Provider de Search configurado",
                "serp_observations",
                "serp_results",
                "serp_competitive_results",
                "DETERMINISTIC-CORRELATIONAL-001",
                "seguro auto online",
                "serpapi",
                "FOUND",
                "ORGANIC_CANDIDATE",
                "QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS",
                "COMPETITOR_CANDIDATE",
                "Article",
                "content-hash-competitor",
                "serp_competitive_ai_analyses",
                "OPENAI",
                "gpt-test",
                "COMPETITIVE-AI-001",
                "Informational / transactional",
                "TOPIC_COVERAGE",
                "CE-CUSTOMER",
                "SCORE-GEO-004",
            ):
                self.assertIn(expected, html)
            self.assertIn("Nenhum indicador desta página altera SARI-001 ou SCORE-GEO-004", html)
            self.assertIn("correlação", html.casefold())

            index = (report / "index.html").read_text(encoding="utf-8")
            self.assertIn("Search Intelligence", index)
            self.assertIn("search-intelligence.html", index)
            self.assertEqual(index.count("search-intelligence-summary"), 1)
            _refresh_search_intelligence_report(root)
            index = (report / "index.html").read_text(encoding="utf-8")
            self.assertEqual(index.count("search-intelligence-summary"), 1)

            surface = surface_by_id("search-intelligence")
            self.assertEqual(surface.filename, "search-intelligence.html")
            self.assertTrue(surface.optional)
            self.assertIn("Nenhum impacto automático", surface.score_impact)

    def test_writer_returns_none_without_serp_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sqlite3.connect(root / "audit.db").close()
            self.assertIsNone(write_search_intelligence_report(root))
            self.assertFalse((root / "report" / "search-intelligence.html").exists())

    @staticmethod
    def _fixture(path: Path) -> None:
        db = sqlite3.connect(path)
        try:
            db.executescript(
                """
                CREATE TABLE serp_observations (
                    observation_id TEXT PRIMARY KEY,audit_id TEXT,run_id TEXT,query TEXT,
                    query_origin TEXT,engine TEXT,country TEXT,region TEXT,language TEXT,
                    device TEXT,collected_at TEXT,provider TEXT,provider_request_id TEXT,
                    requested_depth INTEGER,result_count INTEGER,data_mode TEXT,
                    observation_status TEXT,domain_of_interest TEXT,customer_position INTEGER,
                    domain_status TEXT,raw_evidence_ref TEXT,raw_evidence_sha256 TEXT,
                    config_metadata TEXT,quality_metadata TEXT,error_code TEXT,error_message TEXT
                );
                CREATE TABLE serp_results (
                    observation_id TEXT,position INTEGER,domain TEXT,url TEXT,title TEXT,
                    snippet TEXT,result_type TEXT,serp_features TEXT,metadata TEXT
                );
                CREATE TABLE serp_competitive_analyses (
                    observation_id TEXT PRIMARY KEY,audit_id TEXT,methodology TEXT,
                    comparison_status TEXT,customer_url TEXT,candidate_count INTEGER,
                    observed_competitor_pages INTEGER,gap_count INTEGER,gaps_json TEXT,
                    evidence_ref TEXT,evidence_sha256 TEXT
                );
                CREATE TABLE serp_competitive_results (
                    observation_id TEXT,position INTEGER,domain TEXT,url TEXT,
                    classification TEXT,eligible_for_content_comparison INTEGER,
                    selected_for_content_comparison INTEGER,reason TEXT
                );
                CREATE TABLE serp_competitive_pages (
                    observation_id TEXT,role TEXT,domain TEXT,requested_url TEXT,final_url TEXT,
                    fetch_status TEXT,http_status INTEGER,content_type TEXT,content_sha256 TEXT,
                    bytes_read INTEGER,title TEXT,meta_description TEXT,headings_json TEXT,
                    word_count INTEGER,query_terms_json TEXT,query_terms_title_json TEXT,
                    query_terms_description_json TEXT,query_terms_headings_json TEXT,
                    query_terms_body_json TEXT,jsonld_types_json TEXT,error_code TEXT,
                    error_message TEXT,redirects_json TEXT
                );
                CREATE TABLE serp_competitive_ai_analyses (
                    observation_id TEXT PRIMARY KEY,audit_id TEXT,state TEXT,reason TEXT,
                    provider TEXT,model TEXT,contract_version TEXT,prompt_id TEXT,
                    prompt_version TEXT,provider_request_id TEXT,query_intent TEXT,
                    ymyl_assessment TEXT,summary TEXT,opportunity_count INTEGER,
                    opportunities_json TEXT,evidence_ref TEXT,evidence_sha256 TEXT
                );
                """
            )
            oid = "SERP-OBS-REPORT"
            db.execute(
                "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid,"AUD-REPORT","SERP-RUN-REPORT","seguro auto online","MANUAL","google",
                 "BR","RS","pt-BR","desktop","2026-09-09T04:00:00+00:00","serpapi",
                 "provider-request-1",20,2,"OBSERVED_API","OBSERVED","cliente.example",3,
                 "FOUND","artifacts/search-intelligence/raw.json","raw-hash",
                 '{"surface":"test"}','{"pages_collected":1}',None,None),
            )
            db.executemany(
                "INSERT INTO serp_results VALUES (?,?,?,?,?,?,?,?,?)",
                ((oid,1,"leader.example","https://leader.example/auto","Seguro Auto Líder",
                  "Conteúdo observado","organic",'["snippet"]',"{}"),
                 (oid,3,"cliente.example","https://cliente.example/auto","Seguro Auto Cliente",
                  "Página do cliente","organic","[]","{}")),
            )
            db.execute(
                "INSERT INTO serp_competitive_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (oid,"AUD-REPORT","DETERMINISTIC-CORRELATIONAL-001","CONSOLIDATED",
                 "https://cliente.example/auto",1,1,1,
                 '[{"code":"QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS","severity":"INFO","message":"Cobertura lexical menor.","customer_value":0.5,"leader_reference":1.0,"evidence_urls":["https://leader.example/auto"]}]',
                 "artifacts/search-intelligence/competitive/SERP-OBS-REPORT.json","competitive-hash"),
            )
            db.execute(
                "INSERT INTO serp_competitive_results VALUES (?,?,?,?,?,?,?,?)",
                (oid,1,"leader.example","https://leader.example/auto","ORGANIC_CANDIDATE",1,1,
                 "external organic result; business equivalence is not inferred"),
            )
            common_terms = '["seguro","auto","online"]'
            db.executemany(
                "INSERT INTO serp_competitive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ((oid,"CUSTOMER","cliente.example","https://cliente.example/auto",
                  "https://cliente.example/auto","OBSERVED",200,"text/html","content-hash-customer",
                  1000,"Seguro Auto Cliente","Seguro para seu carro",'["Seguro Auto"]',400,
                  common_terms,'["seguro","auto"]','["seguro"]','["seguro","auto"]',
                  '["seguro","auto"]','["Product"]',None,None,"[]"),
                 (oid,"COMPETITOR_CANDIDATE","leader.example","https://leader.example/auto",
                  "https://leader.example/auto","OBSERVED",200,"text/html","content-hash-competitor",
                  2000,"Seguro Auto Líder","Seguro auto online completo",
                  '["Seguro Auto Online","Coberturas"]',800,common_terms,common_terms,
                  '["seguro","auto"]',common_terms,common_terms,'["Article","Product"]',None,None,"[]")),
            )
            db.execute(
                "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid,"AUD-REPORT","AVAILABLE",None,"OPENAI","gpt-test","COMPETITIVE-AI-001",
                 "competitive_search_content_evidence_v1","1","ai-request-1",
                 "Informational / transactional","Not YMYL for fixture",
                 "A página líder cobre tópico adicional observado.",1,
                 '[{"category":"TOPIC_COVERAGE","priority":"HIGH","title":"Cobrir tópico observado","recommendation":"Adicionar cobertura quando relevante.","rationale":"Diferença semântica apoiada pelas evidências.","evidence_ids":["CE-CUSTOMER","CE-COMP-001"],"confidence":0.82,"causality_note":"Hipótese não causal."}]',
                 "artifacts/search-intelligence/competitive-ai/SERP-OBS-REPORT.json","ai-hash"),
            )
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

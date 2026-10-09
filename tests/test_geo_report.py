"""Focused read-only GEO projection and source-isolation contract tests."""
from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rasai.geo_report import geo_body


class GeoReportTests(unittest.TestCase):
    def test_review_routing_is_advisory_and_category_based(self):
        from rasai.geo_report import _geo_review_routing
        examples = (
            ({"rule_id": "ROBOTS_EXCLUSION"}, "SEO técnico", "crawler"),
            ({"category": "HTML_RENDER"}, "Engenharia Front-end", "DOM renderizado"),
            ({"category": "SEMANTIC_CONTENT"}, "Conteúdo/SEO editorial", "clareza"),
            ({"category": "CITATION_READINESS"}, "Conteúdo/SEO editorial", "clareza"),
            ({"category": "OTHER"}, "área de negócio", "achado original"),
        )
        for finding, owner_fragment, verification_fragment in examples:
            with self.subTest(finding=finding):
                owner, verification = _geo_review_routing(finding)
                self.assertIn(owner_fragment, owner)
                self.assertIn(verification_fragment, verification)
                self.assertNotIn("garantia", verification.lower())


    def test_no_optional_tables_is_explicitly_inconclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE marker (id INTEGER)")
            before = db.read_bytes()
            html = geo_body(db, "AUD-TEST")
            self.assertIn("Não há execução", html)
            self.assertIn("não é possível concluir", html)
            self.assertEqual(before, db.read_bytes())

    def test_sources_are_audit_scoped_and_html_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT, error_class TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                """)
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r1","AUD-ONE",'["question <script>"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r2","AUD-TWO",'["private"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r1",1,"https://www.example.org/path","<bad>","snippet"))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r2",1,"https://different.org","other","other"))
            html = geo_body(db, "AUD-ONE")
            self.assertIn("example.org", html)
            self.assertNotIn("different.org", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)


    def test_cross_source_comparison_requires_single_query_and_observed_api(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT, error_class TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                    CREATE TABLE serp_observations (
                        observation_id TEXT, audit_id TEXT, query TEXT,
                        collected_at TEXT, observation_status TEXT, data_mode TEXT
                    );
                    CREATE TABLE serp_results (
                        observation_id TEXT, url TEXT
                    );
                    CREATE TABLE geo_observation_runs (
                        analysis_id TEXT, audit_id TEXT, projection_json TEXT,
                        created_at TEXT
                    );
                """)
                con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
                            ("r1","AUD-ONE",'["insurance premium"]',"web","SUCCESS","2026-10-07",None))
                con.execute("INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                            ("r1",1,"https://example.org/policy","Policy","snippet"))
                con.execute("INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
                            ("s1","AUD-ONE","insurance premium","2026-10-07","OBSERVED","OBSERVED_API"))
                con.execute("INSERT INTO serp_results VALUES (?,?)",
                            ("s1","https://example.org/policy"))
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?)",
                    ("g1", "AUD-ONE",
                     '{"perplexity_run_id":"r1","serp_observation_id":"s1","serp_url_count":1,'
                     '"perplexity_url_count":1,"url_overlap_count":1,'
                     '"comparability":{"query_equivalent":true,'
                     '"geo_language_device_time_equivalence_proven":false,'
                     '"serp_context":{"country":"BR","region":"São Paulo",'
                     '"language":"pt-BR","device":"mobile","engine":"google",'
                     '"collected_at":"2026-10-07"}}}',
                     "2026-10-07")
                )
            self.assertIn("Sobreposição observacional", geo_body(db, "AUD-ONE"))
            self.assertIn("1 em ambas", geo_body(db, "AUD-ONE"))
            self.assertIn("não comprova escopo de país, idioma, dispositivo", geo_body(db, "AUD-ONE"))
            self.assertIn("País SERP: BR", geo_body(db, "AUD-ONE"))
            self.assertIn("Região SERP: São Paulo", geo_body(db, "AUD-ONE"))
            self.assertIn("Equivalência de país, idioma, dispositivo e instante", geo_body(db, "AUD-ONE"))
            self.assertIn("não comprovada", geo_body(db, "AUD-ONE"))
            # A v4 snapshot can retain source evidence but cannot report
            # noncomparable raw coincidence counts as cross-source overlap.
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?)",
                    ("g2", "AUD-ONE",
                     '{"contract_version":"RASAI-GEO-OBSERVATION-4",'
                     '"perplexity_run_id":"r1","serp_observation_id":"s1",'
                     '"url_overlap_count":1,"serp_url_count":1,"perplexity_url_count":1,'
                     '"descriptive_overlap":{"status":"NOT_COMPARABLE",'
                     '"reason":"TIME_SCOPE_UNPROVEN"},'
                     '"comparability":{"serp_context":{"country":"BR"}}}',
                     "2026-10-09T18:00:00Z"),
                )
            v4 = geo_body(db, "AUD-ONE")
            self.assertIn("Sobreposição observacional de URLs: N/D", v4)
            self.assertIn("instantes de coleta sem relógios verificáveis", v4)
            self.assertNotIn("1 em ambas", v4)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "INSERT INTO geo_observation_runs VALUES (?,?,?,?)",
                    ("g3", "AUD-ONE",
                     '{"contract_version":"RASAI-GEO-OBSERVATION-5",'
                     '"perplexity_run_id":"r1","serp_observation_id":"s1",'
                     '"url_overlap_count":1,"serp_url_count":1,"perplexity_url_count":1,'
                     '"descriptive_overlap":{"status":"NOT_COMPARABLE",'
                     '"reason":"TIME_SCOPE_OUTSIDE_WINDOW"}}',
                     "2026-10-09T19:00:00Z"),
                )
            v5 = geo_body(db, "AUD-ONE")
            self.assertIn("Sobreposição observacional de URLs: N/D", v5)
            self.assertIn("coletas separadas por mais de 24 horas", v5)
            self.assertNotIn("1 em ambas", v5)


    def test_extraction_warning_visible_without_perplexity_run(self):
        from rasai.geo_report import geo_body
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            db = folder / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE placeholder (id TEXT)")
            quality_path = folder / "artifacts" / "geo-extraction-quality.json"
            quality_path.parent.mkdir(parents=True)
            quality_path.write_text(
                '{"observations":[{"state":"NAVIGATION_DOMINATED_SUSPECTED",'
                '"artifact_ref":"artifacts/extraction/SNP-1/main_content.txt",'
                '"word_count":11}]}', encoding="utf-8"
            )
            page = geo_body(db, "AUD-ONE")
            self.assertIn("Confiabilidade da extração principal", page)
            self.assertIn("Não há execução Perplexity Search", page)

    def test_optional_recommendations_with_partial_schema_do_not_break_geo(self):
        from rasai.geo_report import _geo_relevant_findings
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "CREATE TABLE findings (finding_id TEXT, audit_id TEXT, "
                    "rule_id TEXT, category TEXT, severity TEXT, title TEXT, "
                    "evidence_ids TEXT, observed_value TEXT, expected_condition TEXT)"
                )
                con.execute("CREATE TABLE recommendations (finding_id TEXT, title TEXT)")
                con.execute(
                    "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
                    ("F1", "AUD-1", "HTML-1", "HTML", "HIGH", "HTML main empty",
                     "[]", "empty", "content"),
                )
            findings = _geo_relevant_findings(db, "AUD-1")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["finding_id"], "F1")

    def test_geo_section_visual_separation_and_foreign_tld_hint(self):
        from rasai.geo_report import geo_body
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.executescript("""
                    CREATE TABLE perplexity_search_runs (
                        run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                        search_type TEXT, status TEXT, started_at TEXT
                    );
                    CREATE TABLE perplexity_search_sources (
                        run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                    );
                """)
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                    ("PX-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-08")
                )
                con.execute(
                    "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                    ("PX-1", 1, "https://ejemplo.es/seguros", "Seguro", "Fragmento")
                )
            html = geo_body(db, "AUD-1")
            self.assertIn('class="geo-view"', html)
            self.assertIn(".geo-view > section", html)
            self.assertIn("overflow-x:auto", html)
            self.assertLess(html.index("Domínios das fontes observadas"), html.index("Evidências externas para análise competitiva"))
            self.assertIn("TLD estrangeiro", html)
            self.assertIn("ejemplo.es", html)
            self.assertIn("não prova que a fonte seja irrelevante", html)

    def test_existing_competitive_ai_is_reused_only_with_evidence_ids(self):
        from rasai.geo_report import _prior_competitive_ai
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("""
                    CREATE TABLE serp_competitive_ai_analyses (
                        observation_id TEXT, audit_id TEXT, state TEXT,
                        provider TEXT, model TEXT, contract_version TEXT,
                        prompt_id TEXT, prompt_version TEXT, summary TEXT,
                        opportunities_json TEXT, evidence_ref TEXT, evidence_sha256 TEXT
                    )
                """)
                con.execute(
                    "INSERT INTO serp_competitive_ai_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("SERP-1", "AUD-ONE", "AVAILABLE", "TEST", "m1",
                     "COMPETITIVE-AI-001", "p1", "v1", "Hypothesis",
                     '[{"title":"Check clarity","recommendation":"Review headline",'
                     '"evidence_ids":["E1"]},'
                     '{"title":"Uncited guess","recommendation":"Unverifiable",'
                     '"evidence_ids":[]}]',
                     "artifacts/source.json", "deadbeef"),
                )
            matching = _prior_competitive_ai(db, "AUD-ONE", "SERP-1")
            self.assertIsNotNone(matching)
            self.assertEqual(len(matching["opportunities"]), 1)
            self.assertIsNone(_prior_competitive_ai(db, "AUD-TWO", "SERP-1"))
            self.assertIsNone(_prior_competitive_ai(db, "AUD-ONE", "SERP-UNKNOWN"))


if __name__ == "__main__":
    unittest.main()


def test_primary_geo_page_current_status_uses_utc_instead_of_lexicographic_time(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT, error_class TEXT);
            CREATE TABLE perplexity_search_sources(
                run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT);
        """)
        con.executemany(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
            [
                ("OLD-SUCCESS", "AUD-1", '["seguro de vida"]', "web", "SUCCESS",
                 "2026-10-09T11:30:00+00:00", None),
                ("NEW-ERROR", "AUD-1", '["seguro de vida"]', "web", "RATE_LIMIT_ERROR",
                 "2026-10-09T09:00:00-03:00", "RATE_LIMIT_ERROR"),
            ],
        )
        con.execute(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
            ("OLD-SUCCESS", 1, "https://example.org/a", "Fonte", "Snippet"),
        )
    before = db.read_bytes()
    html = geo_body(db, "AUD-1")
    assert "Estado mais recente: <strong>RATE_LIMIT_ERROR</strong>" in html
    assert "Estado mais recente: <strong>SUCCESS</strong>" not in html
    assert "OLD-SUCCESS" in html  # historical evidence remains visible, not latest
    assert "NEW-ERROR" in html
    assert db.read_bytes() == before


def test_primary_geo_page_does_not_promote_old_success_without_credible_clock(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT);
            CREATE TABLE perplexity_search_sources(
                run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT);
        """)
        con.executemany(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            [
                ("OLD-SUCCESS", "AUD-1", '["seguro de vida"]', "web",
                 "SUCCESS", "2026-10-09"),
                ("NEW-FAILED", "AUD-1", '["seguro de vida"]', "web",
                 "NETWORK_ERROR", "2026-10-10"),
            ],
        )
    before = db.read_bytes()
    html = geo_body(db, "AUD-1")
    assert "Estado mais recente: <strong>N/D</strong>" in html
    assert "Estado mais recente: <strong>SUCCESS</strong>" not in html
    assert "cronologia UTC verificável" in html
    assert db.read_bytes() == before


def test_primary_geo_ai_report_uses_newest_actual_utc_attempt_for_same_run(tmp_path):
    from rasai.geo_report import _geo_ai_result
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE geo_ai_interpretations("
            "audit_id TEXT, perplexity_run_id TEXT, result_id TEXT, "
            "state TEXT, provider TEXT, model TEXT, prompt_id TEXT, "
            "prompt_version TEXT, summary TEXT, opportunities_json TEXT, "
            "input_sha256 TEXT, error_reason TEXT, created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("AUD-1", "RUN-1", "OLD", "AVAILABLE", "TEST", "m", "p",
                 "v", "antiga", "[]", "hash1", None,
                 "2026-10-09T11:30:00+00:00"),
                ("AUD-1", "RUN-1", "NEW", "UNAVAILABLE", "TEST", "m", "p",
                 "v", "", "[]", "hash2", "timeout",
                 "2026-10-09T09:00:00-03:00"),
            ],
        )
    before = db.read_bytes()
    latest = _geo_ai_result(db, "AUD-1", "RUN-1")
    assert latest is not None
    assert latest["state"] == "UNAVAILABLE"
    assert latest["summary"] == ""
    with sqlite3.connect(db) as con:
        con.execute("UPDATE geo_ai_interpretations SET created_at=NULL WHERE result_id='NEW'")
    assert _geo_ai_result(db, "AUD-1", "RUN-1") is None
    assert db.read_bytes() != before  # mutation belongs only to test fixture


def test_geo_page_explains_durable_uncertain_ai_intent_without_publishing_success(
    tmp_path,
):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT, error_class TEXT);
            CREATE TABLE perplexity_search_sources(
                run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT);
            CREATE TABLE geo_ai_interpretations(
                audit_id TEXT, perplexity_run_id TEXT, state TEXT,
                provider TEXT, model TEXT, prompt_id TEXT, prompt_version TEXT,
                summary TEXT, opportunities_json TEXT, input_sha256 TEXT,
                error_reason TEXT, created_at TEXT);
        """)
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?)",
            ("P1", "AUD-A", '["seguro"]', "web", "SUCCESS",
             "2026-10-09T09:00:00+00:00", None),
        )
        con.execute(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
            ("P1", 1, "https://external.example/evidence", "Title", "Excerpt"),
        )
        con.execute(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AUD-A", "P1", "PENDING_UNCERTAIN", None, None, None, None,
             None, "[]", "testhash", "GEO_AI_OUTCOME_NOT_YET_PERSISTED",
             "2026-10-09T09:01:00+00:00"),
        )
    before = db.read_bytes()
    page = geo_body(db, "AUD-A")
    assert "Resultado indeterminado" in page
    assert "pode existir cobrança" in page.lower()
    assert "bloqueia novo envio" in page
    assert "Sem oportunidade com referência de evidência validada." not in page
    assert db.read_bytes() == before


def test_geo_stored_overlap_uses_utc_order_and_abstains_on_ambiguous_history(
    tmp_path,
):
    from rasai.geo_report import _stored_comparison
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE geo_observation_runs("
            "audit_id TEXT, analysis_id TEXT, projection_json TEXT, created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO geo_observation_runs VALUES (?,?,?,?)",
            [
                ("AUD-A", "LEXICAL-Z-OLD", '{"marker":"OLD"}',
                 "2026-10-09T11:30:00+00:00"),
                ("AUD-A", "LEXICAL-A-NEW", '{"marker":"NEW"}',
                 "2026-10-09T09:00:00-03:00"),
                ("AUD-B", "OTHER-AUD", '{"marker":"SECRET"}',
                 "2026-10-09T23:00:00+00:00"),
            ],
        )
    before = db.read_bytes()
    assert _stored_comparison(db, "AUD-A") == {"marker": "NEW"}
    assert "SECRET" not in str(_stored_comparison(db, "AUD-A"))
    assert db.read_bytes() == before

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE geo_observation_runs SET created_at=? WHERE analysis_id=?",
            ("2026-10-09T12:00:00Z", "LEXICAL-Z-OLD"),
        )
    before_tie = db.read_bytes()
    assert _stored_comparison(db, "AUD-A") is None
    assert db.read_bytes() == before_tie

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE geo_observation_runs SET created_at=? WHERE analysis_id=?",
            ("2026-10-09", "LEXICAL-Z-OLD"),
        )
    before_naive = db.read_bytes()
    assert _stored_comparison(db, "AUD-A") is None
    assert db.read_bytes() == before_naive

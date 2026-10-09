"""#308: same-AUD CAT projections, read-only, no invented GEO effects."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.geo_catalog_context import catalog_geo_context


def _db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE findings (
                audit_id TEXT, finding_id TEXT, category TEXT,
                rule_id TEXT, title TEXT, evidence_ids TEXT
            );
            CREATE TABLE recommendations (
                audit_id TEXT, finding_id TEXT, title TEXT, priority_class TEXT
            );
            CREATE TABLE serp_observations (
                audit_id TEXT, observation_id TEXT, query TEXT,
                data_mode TEXT, observation_status TEXT
            );
            CREATE TABLE geo_ai_interpretations (
                audit_id TEXT, result_id TEXT, state TEXT
            );
        """)
        con.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?)", [
            ("AUD-1", "F-TECH", "INDEXABILITY", "R-CANON", "Canonical suspeita",
             '["EV-TECH"]'),
            ("AUD-1", "F-CONTENT", "ENTITY_CLARITY", "R-ENTITY",
             "Entidade não descrita", '["EV-CONTENT"]'),
            ("AUD-1", "F-EMPTY", "CONTENT", "R-EMPTY", "Sem ref", "[]"),
            ("AUD-1", "F-OTHER", "PERFORMANCE", "R-LCP", "LCP lento", '["EV-PERF"]'),
            ("AUD-2", "F-PRIVATE", "INDEXABILITY", "SECRET",
             "SEGREDO-DA-OUTRA-AUD", '["EV-SECRET"]'),
            ("AUD-1", "F-ESCAPE", "CONTENT", "R-XSS",
             "<script>leak</script>", '["EV-XSS"]'),
        ])
        con.executemany("INSERT INTO recommendations VALUES (?,?,?,?)", [
            ("AUD-1", "F-TECH", "Rever canonical", "P1"),
            ("AUD-1", "F-TECH", "Rever canonical", "P1"),  # replay duplicate
            ("AUD-1", "F-CONTENT", "Rever entidade", "P2"),
            ("AUD-1", "F-OTHER", "Melhorar LCP", "P1"),
            ("AUD-2", "F-PRIVATE", "SEGREDO-RECOMENDACAO", "P1"),
        ])
        con.executemany("INSERT INTO serp_observations VALUES (?,?,?,?,?)", [
            ("AUD-1", "SERP-REAL", "seguro", "OBSERVED_API", "OBSERVED"),
            ("AUD-1", "SERP-SYNTH", "preview", "SYNTHETIC", "OBSERVED"),
            ("AUD-2", "SERP-PRIVATE", "SEGREDO-QUERY", "OBSERVED_API", "OBSERVED"),
        ])
        con.executemany("INSERT INTO geo_ai_interpretations VALUES (?,?,?)", [
            ("AUD-1", "GEOAI-OK", "AVAILABLE"),
            ("AUD-2", "GEOAI-SECRET", "AVAILABLE"),
        ])


def test_cat_projection_uses_only_category_owned_evidence_and_filters_other_aud(tmp_path):
    db = tmp_path / "audit.db"
    _db(db)
    before = db.read_bytes()
    c1 = catalog_geo_context(db, "AUD-1", "CAT-01")
    c3 = catalog_geo_context(db, "AUD-1", "CAT-03")
    c5 = catalog_geo_context(db, "AUD-1", "CAT-05")
    c8 = catalog_geo_context(db, "AUD-1", "CAT-08")
    c9 = catalog_geo_context(db, "AUD-1", "CAT-09")
    assert "F-TECH" in c1 and "EV-TECH" in c1
    assert "F-CONTENT" not in c1 and "F-EMPTY" not in c1
    assert "F-CONTENT" in c3 and "F-TECH" not in c3
    assert "<script>leak</script>" not in c3
    assert "&lt;script&gt;leak&lt;/script&gt;" in c3
    assert "SERP-REAL" in c5 and "SERP-SYNTH" not in c5
    assert "GEOAI-OK" in c8 and "GEOAI-SECRET" not in c8
    assert "Rever canonical" in c9 and "Rever entidade" in c9
    assert c9.count("Rever canonical") == 1  # no duplicate GEO action from replay
    assert "Melhorar LCP" not in c9
    for html in (c1, c3, c5, c8, c9):
        assert "SEGREDO" not in html
        assert "geo.html" in html
    assert db.read_bytes() == before


def test_legacy_schema_abstains_without_writes(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE findings(audit_id TEXT, finding_id TEXT)")
    original = db.read_bytes()
    for cat in ("CAT-01", "CAT-03", "CAT-05", "CAT-08", "CAT-09"):
        html = catalog_geo_context(db, "LEGACY", cat)
        assert "geo.html" in html
        assert "<section>" in html
    assert catalog_geo_context(db, "LEGACY", "CAT-07") == ""
    assert db.read_bytes() == original


def test_cat08_without_ai_does_not_claim_interpretation(tmp_path):
    db = tmp_path / "audit.db"
    _db(db)
    output = catalog_geo_context(db, "AUD-3", "CAT-08")
    assert "Sem interpretação GEO por IA disponível" in output
    assert "GEOAI-OK" not in output




def test_strategic_geo_surfaces_expose_only_persisted_same_aud_status(tmp_path):
    from rasai.geo_catalog_context import geo_surface_context
    db = tmp_path / "audit.db"
    _db(db)
    original = db.read_bytes()
    index = geo_surface_context(db, "AUD-1", "index")
    directed = geo_surface_context(db, "AUD-1", "directed-analysis")
    integrations = geo_surface_context(db, "AUD-1", "ai-integrations")
    assert "SERP-REAL" not in index
    assert "Perplexity Search não solicitada" in index
    for page in (index, directed, integrations):
        assert "geo.html" in page
    assert db.read_bytes() == original

    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE perplexity_search_runs("
            "run_id TEXT, audit_id TEXT, status TEXT, started_at TEXT)"
        )
        con.execute(
            "CREATE TABLE perplexity_search_sources("
            "run_id TEXT, url TEXT)"
        )
        con.executemany("INSERT INTO perplexity_search_runs VALUES (?,?,?,?)", [
            ("RUN-1", "AUD-1", "SUCCESS", "2026-10-09"),
            ("RUN-2", "AUD-2", "CREDIT_ERROR", "2026-10-09"),
        ])
        con.executemany("INSERT INTO perplexity_search_sources VALUES (?,?)", [
            ("RUN-1", "https://evidence.test/a"),
            ("RUN-1", "https://evidence.test/b"),
            ("RUN-2", "https://secret.other/x"),
        ])
    overview = geo_surface_context(db, "AUD-1", "index")
    directed = geo_surface_context(db, "AUD-1", "directed-analysis")
    integrations = geo_surface_context(db, "AUD-1", "ai-integrations")
    assert "RUN-1" in overview and "SUCCESS" in overview
    assert "Fontes externas retornadas: 2" in overview
    assert "RUN-2" not in overview and "CREDIT_ERROR" not in overview
    assert "não significa que" in directed
    assert "não recontabiliza gasto" in integrations
    assert geo_surface_context(db, "AUD-1", "cat-07") == ""


def test_surface_context_escapes_status_and_id(tmp_path):
    from rasai.geo_catalog_context import geo_surface_context
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE perplexity_search_runs(run_id TEXT,audit_id TEXT,status TEXT)")
        con.execute("INSERT INTO perplexity_search_runs VALUES (?,?,?)",
                    ("<img>", "AUD-S", "<script>"))
    html = geo_surface_context(db, "AUD-S", "index")
    assert "<script>" not in html and "<img>" not in html
    assert "&lt;script&gt;" in html and "&lt;img&gt;" in html



def test_crossrefs_use_actual_observation_timestamps_not_opaque_ids(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE serp_observations (
              audit_id TEXT, observation_id TEXT, query TEXT,
              data_mode TEXT, observation_status TEXT, collected_at TEXT
            );
            CREATE TABLE geo_ai_interpretations (
              audit_id TEXT, result_id TEXT, state TEXT, created_at TEXT
            );
        """)
        con.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?)", [
                ("AUD-1", "SERP-Z-OLDER", "consulta antiga", "OBSERVED_API",
                 "OBSERVED", "2026-10-07T10:00:00+00:00"),
                ("AUD-1", "SERP-A-NEWER", "consulta atual", "OBSERVED_API",
                 "OBSERVED", "2026-10-09T10:00:00+00:00"),
                ("AUD-2", "SERP-PRIVATE", "não mostrar", "OBSERVED_API",
                 "OBSERVED", "2026-12-01T10:00:00+00:00"),
            ],
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?)", [
                ("AUD-1", "GEOAI-Z-OLDER", "AVAILABLE", "2026-10-07T10:00:00+00:00"),
                ("AUD-1", "GEOAI-A-NEWER", "AVAILABLE", "2026-10-09T10:00:00+00:00"),
                ("AUD-1", "GEOAI-UNAVAILABLE", "FAILED", "2026-12-01T10:00:00+00:00"),
                ("AUD-2", "GEOAI-PRIVATE", "AVAILABLE", "2026-12-01T10:00:00+00:00"),
            ],
        )
    before = db.read_bytes()
    search = catalog_geo_context(db, "AUD-1", "CAT-05")
    advisory = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "SERP-A-NEWER" in search and "SERP-Z-OLDER" not in search
    assert "FAILED" in advisory and "última tentativa" in advisory
    assert "GEOAI-A-NEWER" not in advisory and "GEOAI-Z-OLDER" not in advisory
    assert "SERP-PRIVATE" not in search
    assert "GEOAI-PRIVATE" not in advisory
    assert db.read_bytes() == before


def test_cat08_does_not_promote_older_success_after_latest_unavailable(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE geo_ai_interpretations("
            "audit_id TEXT, result_id TEXT, state TEXT, created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?)",
            [
                ("AUD-1", "OLD-AVAILABLE", "AVAILABLE",
                 "2026-10-08T10:00:00+00:00"),
                ("AUD-1", "NEW-UNAVAILABLE", "UNAVAILABLE",
                 "2026-10-09T10:00:00+00:00"),
                ("AUD-2", "PRIVATE-AVAILABLE", "AVAILABLE",
                 "2026-11-09T10:00:00+00:00"),
            ],
        )
    before = db.read_bytes()
    output = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "UNAVAILABLE" in output
    assert "OLD-AVAILABLE" not in output
    assert "NEW-UNAVAILABLE" not in output
    assert "PRIVATE-AVAILABLE" not in output
    assert db.read_bytes() == before

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE geo_ai_interpretations SET state='AVAILABLE' "
            "WHERE result_id='NEW-UNAVAILABLE'"
        )
    eligible = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "NEW-UNAVAILABLE" in eligible
    assert "OLD-AVAILABLE" not in eligible


def test_cat08_terminal_state_is_html_escaped(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE geo_ai_interpretations("
            "audit_id TEXT, result_id TEXT, state TEXT)"
        )
        con.execute(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?)",
            ("AUD-1", "AI-X", "<script>bad</script>"),
        )
    output = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "<script>bad</script>" not in output
    assert "&lt;script&gt;" in output


def test_crossrefs_compare_real_utc_instants_not_iso_strings_or_opaque_ids(tmp_path):
    from rasai.geo_catalog_context import geo_surface_context
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE serp_observations(
                observation_id TEXT, audit_id TEXT, query TEXT,
                collected_at TEXT, data_mode TEXT, observation_status TEXT);
            CREATE TABLE geo_ai_interpretations(
                result_id TEXT, audit_id TEXT, state TEXT, created_at TEXT);
            CREATE TABLE perplexity_search_runs(
                run_id TEXT, audit_id TEXT, status TEXT, started_at TEXT);
        """)
        con.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?)",
            [
                ("SERP-Z-OLDER", "AUD-1", "antiga", "2026-10-09T11:30:00+00:00",
                 "OBSERVED_API", "OBSERVED"),
                ("SERP-A-NEWER", "AUD-1", "atual", "2026-10-09T09:00:00-03:00",
                 "OBSERVED_API", "OBSERVED"),
                ("SERP-FOREIGN", "AUD-2", "segredo", "2026-12-01T00:00:00+00:00",
                 "OBSERVED_API", "OBSERVED"),
            ],
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?)",
            [
                ("GEO-OLD-AVAILABLE", "AUD-1", "AVAILABLE",
                 "2026-10-09T11:30:00+00:00"),
                ("GEO-NEW-FAILED", "AUD-1", "FAILED",
                 "2026-10-09T09:00:00-03:00"),
                ("GEO-FOREIGN", "AUD-2", "AVAILABLE",
                 "2026-12-01T00:00:00+00:00"),
            ],
        )
        con.executemany(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?)",
            [
                ("RUN-OLD", "AUD-1", "SUCCESS", "2026-10-09T11:30:00+00:00"),
                ("RUN-NEW", "AUD-1", "RATE_LIMIT_ERROR", "2026-10-09T09:00:00-03:00"),
                ("RUN-FOREIGN", "AUD-2", "SUCCESS", "2026-12-01T00:00:00+00:00"),
            ],
        )
    before = db.read_bytes()
    search = catalog_geo_context(db, "AUD-1", "CAT-05")
    interpretation = catalog_geo_context(db, "AUD-1", "CAT-08")
    overview = geo_surface_context(db, "AUD-1", "index")
    assert "SERP-A-NEWER" in search and "SERP-Z-OLDER" not in search
    assert "FAILED" in interpretation and "GEO-OLD-AVAILABLE" not in interpretation
    assert "RATE_LIMIT_ERROR" in overview
    assert "RUN-NEW" in overview and "RUN-OLD" not in overview
    assert "FOREIGN" not in search + interpretation + overview
    assert db.read_bytes() == before


def test_crossrefs_abstain_on_ambiguous_history_instead_of_promoting_old_success(
    tmp_path,
):
    from rasai.geo_catalog_context import geo_surface_context
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE serp_observations(
                observation_id TEXT, audit_id TEXT, query TEXT,
                data_mode TEXT, observation_status TEXT);
            CREATE TABLE geo_ai_interpretations(
                result_id TEXT, audit_id TEXT, state TEXT);
            CREATE TABLE perplexity_search_runs(
                run_id TEXT, audit_id TEXT, status TEXT);
        """)
        con.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?)",
            [
                ("SERP-Z", "AUD-1", "uma", "OBSERVED_API", "OBSERVED"),
                ("SERP-A", "AUD-1", "outra", "OBSERVED_API", "OBSERVED"),
            ],
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?)",
            [("GEO-Z", "AUD-1", "AVAILABLE"), ("GEO-A", "AUD-1", "FAILED")],
        )
        con.executemany(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?)",
            [("RUN-Z", "AUD-1", "SUCCESS"), ("RUN-A", "AUD-1", "TIMEOUT_ERROR")],
        )
    before = db.read_bytes()
    search = catalog_geo_context(db, "AUD-1", "CAT-05")
    geoai = catalog_geo_context(db, "AUD-1", "CAT-08")
    external = geo_surface_context(db, "AUD-1", "index")
    assert "cronologia não" in search and "mais recente N/D" in search
    assert "último estado N/D" in geoai and "AVAILABLE" not in geoai
    assert "última execução N/D" in external and "SUCCESS" not in external
    assert all(key not in search for key in ("SERP-Z", "SERP-A"))
    assert all(key not in geoai for key in ("GEO-Z", "GEO-A"))
    assert all(key not in external for key in ("RUN-Z", "RUN-A"))
    assert db.read_bytes() == before


def test_multiple_tied_or_invalid_clocks_cannot_establish_last_ai_attempt(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE geo_ai_interpretations("
            "result_id TEXT, audit_id TEXT, state TEXT, created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?)",
            [
                ("A1", "AUD-1", "AVAILABLE", "2026-10-09T12:00:00+00:00"),
                ("A2", "AUD-1", "FAILED", "2026-10-09T09:00:00-03:00"),
            ],
        )
    outcome = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "último estado N/D" in outcome
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE geo_ai_interpretations SET created_at=NULL WHERE result_id='A2'"
        )
    second = catalog_geo_context(db, "AUD-1", "CAT-08")
    assert "último estado N/D" in second
    assert "A1" not in second and "A2" not in second

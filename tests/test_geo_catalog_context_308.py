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


def test_existing_report_materialization_uses_context_by_catalog(tmp_path):
    from test_catalog_report_site import _workspace, AUDIT_ID
    from rasai.catalog_report_site import materialize_catalog_report_site

    workspace, _ = _workspace(tmp_path)
    with sqlite3.connect(workspace.database) as con:
        con.execute(
            "CREATE TABLE findings(audit_id TEXT, finding_id TEXT, category TEXT, "
            "rule_id TEXT, title TEXT, evidence_ids TEXT)"
        )
        con.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?)",
            (AUDIT_ID, "GEO-CAT1", "INDEXABILITY", "R-INDEX",
             "Inspecionar indexação", '["EV-INDEX"]'),
        )
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    cat1 = (report / "cat-01.html").read_text(encoding="utf-8")
    cat3 = (report / "cat-03.html").read_text(encoding="utf-8")
    assert "GEO-CAT1" in cat1 and "EV-INDEX" in cat1
    assert "GEO-CAT1" not in cat3

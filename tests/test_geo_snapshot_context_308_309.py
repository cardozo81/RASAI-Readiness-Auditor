"""#308/#309: same-AUD, latest-request GEO contextual evidence on report surfaces.

Read-only legacy compatibility, no paid API, stale snapshots, or artificial
prioritization. Fixture intentionally uses persisted snapshot schema/derived ID
and different audit's private evidence to detect cross-AUD data leaks.
"""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

from rasai.geo_catalog_context import catalog_geo_context, geo_surface_context
from rasai.geo_snapshot_context_308 import persisted_geo_scope


def _prepare(path, *, status="SUCCESS", newer_failure=False, invalid=False):
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY,audit_id TEXT,status TEXT,started_at TEXT
            );
            CREATE TABLE geo_observation_runs(
                analysis_id TEXT PRIMARY KEY, audit_id TEXT,
                perplexity_run_id TEXT, contract_version TEXT,
                input_sha256 TEXT, projection_json TEXT, created_at TEXT
            );
        """)
        con.executemany("INSERT INTO perplexity_search_runs VALUES(?,?,?,?)", [
            ("RUN-OK", "AUD-A", status, "2026-10-09T10:00:00+00:00"),
            ("RUN-FOREIGN", "AUD-B", "SUCCESS", "2026-10-09T12:00:00+00:00"),
        ])
        if newer_failure:
            con.execute(
                "INSERT INTO perplexity_search_runs VALUES(?,?,?,?)",
                ("RUN-FAILED", "AUD-A", "CREDIT_ERROR",
                 "2026-10-09T11:00:00+00:00"),
            )
        digest = sha256(b"source-and-query").hexdigest()
        version = "RASAI-GEO-OBSERVATION-8"
        identifier = "GEO-" + sha256(
            ("AUD-A:" + version + ":" + digest).encode()
        ).hexdigest()[:32].upper()
        target = {
            "status": "DOMAIN_ALTERNATIVE_OBSERVED",
            "query": "seguro vida",
            "evidence_run_id": "RUN-OK",
            "target_url": "https://example.org/vida",
            "recommendation": "Revisar intenção e organização da oferta",
        }
        projection = {
            "contract_version": version,
            "audit_id": "AUD-A",
            "perplexity_run_id": "RUN-OK",
            "search_status": "SUCCESS",
            "queries": ["seguro vida"],
            "target_observation": target,
            "descriptive_overlap": {
                "status": "DESCRIPTIVE_ONLY",
                "serp_denominator": 10,
                "perplexity_denominator": 4,
                "common_urls": 2,
                "jaccard_url_rate": 0.1667,
            },
        }
        if invalid:
            projection["audit_id"] = "AUD-B"
        con.execute(
            "INSERT INTO geo_observation_runs VALUES(?,?,?,?,?,?,?)",
            (identifier, "AUD-A", "RUN-OK", version, digest,
             json.dumps(projection), "2026-10-09T10:15:00+00:00"),
        )
        con.execute(
            "INSERT INTO geo_observation_runs VALUES(?,?,?,?,?,?,?)",
            ("GEO-FOREIGN", "AUD-B", "RUN-FOREIGN", version, digest,
             '{"private":"DO_NOT_RENDER"}', "2026-10-09T12:15:00+00:00"),
        )


def test_all_five_catalogs_and_strategic_surfaces_are_evidence_scoped(tmp_path):
    db = tmp_path / "audit.db"
    _prepare(db)
    frozen = db.read_bytes()
    by_cat = {
        "CAT-01": "não comprova defeito técnico",
        "CAT-03": "outra URL do domínio",
        "CAT-05": "2 em comum; SERP 2/10; Perplexity 2/4",
        "CAT-08": "não muda prioridade",
        "CAT-09": "Revisar intenção e organização da oferta",
    }
    for cat, phrase in by_cat.items():
        html = catalog_geo_context(db, "AUD-A", cat)
        assert phrase in html
        assert "seguro vida" in html
        assert "DOMAIN_ALTERNATIVE_OBSERVED" in html
        assert "DO_NOT_RENDER" not in html
    for surface in ("index", "directed-analysis", "ai-integrations"):
        html = geo_surface_context(db, "AUD-A", surface)
        assert "RUN-OK" in html
        assert "seguro vida" in html
        assert "DO_NOT_RENDER" not in html
    assert db.read_bytes() == frozen
    assert catalog_geo_context(db, "AUD-A", "CAT-07") == ""


def test_later_failed_search_must_hide_old_successful_snapshot_on_every_surface(tmp_path):
    db = tmp_path / "audit.db"
    _prepare(db, newer_failure=True)
    baseline = db.read_bytes()
    for cat in ("CAT-01", "CAT-03", "CAT-05", "CAT-08", "CAT-09"):
        html = catalog_geo_context(db, "AUD-A", cat)
        assert "Correlação GEO por snapshot: N/D" in html
        assert "LATEST_SEARCH_NOT_SUCCESSFUL" in html
        assert "seguro vida" not in html
        assert "Revisar intenção" not in html
        assert "2 em comum" not in html
    for page in ("index", "directed-analysis", "ai-integrations"):
        html = geo_surface_context(db, "AUD-A", page)
        assert "CREDIT_ERROR" in html
        assert "LATEST_SEARCH_NOT_SUCCESSFUL" in html
        assert "seguro vida" not in html
    assert db.read_bytes() == baseline


def test_failed_or_cross_aud_snapshot_cannot_be_presented_as_correlated(tmp_path):
    for options, reason in [
        ({"status": "TIMEOUT"}, "LATEST_SEARCH_NOT_SUCCESSFUL"),
        ({"invalid": True}, "SNAPSHOT_RECORD_UNVERIFIABLE"),
    ]:
        path = tmp_path / (reason + ".db")
        _prepare(path, **options)
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as con:
            actual, projection = persisted_geo_scope(con, "AUD-A")
        assert actual == reason
        assert projection is None
        output = catalog_geo_context(path, "AUD-A", "CAT-05")
        assert "sobreposição descritiva" not in output.lower()
        assert "2 em comum" not in output
        assert "DO_NOT_RENDER" not in output


def test_ambiguous_latest_search_clock_never_promotes_prior_snapshot(tmp_path):
    db = tmp_path / "audit.db"
    _prepare(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES(?,?,?,?)",
            ("RUN-TIED", "AUD-A", "FAILED", "2026-10-09T07:00:00-03:00"),
        )
    before = db.read_bytes()
    for surface in ("CAT-03", "CAT-05", "CAT-09"):
        output = catalog_geo_context(db, "AUD-A", surface)
        assert "LATEST_REQUEST_CHRONOLOGY_UNVERIFIABLE" in output
        assert "seguro vida" not in output
    assert db.read_bytes() == before


def test_xss_from_persisted_search_is_escaped_and_foreign_evidence_hidden(tmp_path):
    db = tmp_path / "audit.db"
    _prepare(db)
    with sqlite3.connect(db) as con:
        row = con.execute(
            "SELECT projection_json FROM geo_observation_runs WHERE audit_id='AUD-A'"
        ).fetchone()
        projection = json.loads(row[0])
        projection["queries"] = ["<script>seguro vida</script>"]
        projection["target_observation"]["query"] = "<script>seguro vida</script>"
        projection["target_observation"]["recommendation"] = "<img src=x onerror=alert(1)>"
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=? WHERE audit_id='AUD-A'",
            (json.dumps(projection),),
        )
    html = catalog_geo_context(db, "AUD-A", "CAT-09")
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert "DO_NOT_RENDER" not in html


def test_legacy_schema_no_search_or_snapshot_returns_nd_without_sqlite_writes(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
    before = db.read_bytes()
    html = catalog_geo_context(db, "AUD-OLD", "CAT-05")
    assert "N/D" in html
    assert "geo.html" in html
    assert db.read_bytes() == before


def test_missing_or_inconsistent_url_denominators_abstain_in_cat05(tmp_path):
    db = tmp_path / "audit.db"
    _prepare(db)
    with sqlite3.connect(db) as con:
        row = con.execute("SELECT projection_json FROM geo_observation_runs WHERE audit_id='AUD-A'").fetchone()
        payload = json.loads(row[0])
        payload["descriptive_overlap"]["common_urls"] = 11
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=? WHERE audit_id='AUD-A'",
            (json.dumps(payload),),
        )
    html = catalog_geo_context(db, "AUD-A", "CAT-05")
    assert "denominadores persistidos inconsistentes" in html
    assert "2 em comum" not in html

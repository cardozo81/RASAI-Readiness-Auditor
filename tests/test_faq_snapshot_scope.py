"""#601 physical snapshot URL/device/identity scope for FAQ; no collector/score."""
from __future__ import annotations

import sqlite3

from rasai.faq_snapshot_scope import read_faq_snapshot_scopes
from rasai.faq_observation import faq_observation_html


def _audit(tmp_path):
    root = tmp_path / "AUD-FAQ-SCOPE"
    evidence = root / "artifacts" / "rendered"
    evidence.mkdir(parents=True)
    (evidence / "one.html").write_text(
        '<button aria-controls="faq-answer" aria-expanded="false">FAQ</button>',
        encoding="utf-8",
    )
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,rendered_artifact_ref TEXT,"
            "requested_url TEXT,final_url TEXT,device TEXT);"
        )
        con.execute("INSERT INTO pages VALUES (?,?)", ("PAGE-1", root.name))
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "PAGE-1", "artifacts/rendered/one.html",
             "https://site.test/faq", "https://site.test/faq", "mobile"),
        )
    return db


def test_601_cat03_report_exposes_physical_url_device_page_snapshot_without_click(
    tmp_path,
):
    db = _audit(tmp_path)
    before_db = db.read_bytes()
    before_html = (db.parent / "artifacts/rendered/one.html").read_bytes()
    html = faq_observation_html(db, db.parent.name)
    assert "Proveniência por captura" in html
    assert "<th>Page ID</th>" in html and "<th>Dispositivo</th>" in html
    assert "<code>SNP-1</code>" in html
    assert "<code>PAGE-1</code>" in html
    assert "<td>MOBILE</td>" in html
    assert "https://site.test/faq" in html
    assert "N/D quando não existe recibo autenticado" in html
    assert "BR-GEO-039" in html and "BR-GEO-049" in html
    assert db.read_bytes() == before_db
    assert (db.parent / "artifacts/rendered/one.html").read_bytes() == before_html


def test_601_global_duplicate_snapshot_id_other_audit_abstains(tmp_path):
    db = _audit(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO pages VALUES ('OTHER','AUD-DIFFERENT')")
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "OTHER", "artifacts/rendered/other.html",
             "https://other.test/", "https://other.test/", "desktop"),
        )
    html = faq_observation_html(db, "AUD-FAQ-SCOPE")
    assert "Snapshot IDs ausentes ou duplicados: N/D" in html
    assert "Foram identificados" not in html


def test_601_legacy_schema_keeps_observation_but_scope_is_nd(tmp_path):
    root = tmp_path / "AUD-LEGACY-FAQ"
    artifact = root / "artifacts/rendered/page.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        '<button aria-controls="faq-x" aria-expanded="false">Q</button>',
        encoding="utf-8",
    )
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,rendered_artifact_ref TEXT);"
            "INSERT INTO pages VALUES ('PAGE','AUD-LEGACY-FAQ');"
            "INSERT INTO page_snapshots VALUES "
            "('SNAP','PAGE','artifacts/rendered/page.html');"
        )
    report = faq_observation_html(db, root.name)
    assert "<code>SNAP</code>" in report
    assert "<code>PAGE</code>" in report
    assert "<td>N/D</td>" in report
    assert "não prova ausência editorial" in report.lower()


def test_601_invalid_scope_metadata_never_becomes_verified_url(tmp_path):
    db = _audit(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE page_snapshots SET requested_url=?,final_url=?,device=?",
            ("https://evil.test/<img src=x>", "https://user@site.test/faq", "invalid"),
        )
        con.execute("PRAGMA query_only=ON")
        rows, _, status = read_faq_snapshot_scopes(
            con, "AUD-FAQ-SCOPE",
        )
    assert status == "OBSERVATIONAL_SCOPE_ONLY"
    assert rows[0].requested_url == "https://evil.test/<img src=x>"
    assert rows[0].final_url == "N/D"
    assert rows[0].device == "N/D"
    html = faq_observation_html(db, "AUD-FAQ-SCOPE")
    assert "&lt;img src=x&gt;" in html
    assert "<img src=x>" not in html
    assert "<td>N/D</td>" in html


def test_601_duplicate_beyond_display_limit_invalidates_whole_source(tmp_path):
    db = _audit(tmp_path)
    with sqlite3.connect(db) as con:
        for index in range(2, 16):
            con.execute(
                "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                (f"SNP-{index:02}", "PAGE-1", "artifacts/rendered/missing.html",
                 "https://site.test/faq", "https://site.test/faq", "mobile"),
            )
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "PAGE-1", "artifacts/rendered/missing.html",
             "https://site.test/faq", "https://site.test/faq", "mobile"),
        )
    assert "Snapshot IDs ausentes ou duplicados: N/D" in faq_observation_html(
        db, "AUD-FAQ-SCOPE",
    )


def test_601_duplicate_entirely_outside_display_limit_fails_closed(tmp_path):
    db = _audit(tmp_path)
    with sqlite3.connect(db) as con:
        for number in range(2, 16):
            con.execute(
                "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                (f"SNP-{number:02}", "PAGE-1", "artifacts/rendered/missing.html",
                 "https://site.test/faq", "https://site.test/faq", "mobile"),
            )
        # SNP-14 is not among the first 13 ordered display rows.
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-14", "PAGE-1", "artifacts/rendered/missing.html",
             "https://site.test/faq", "https://site.test/faq", "mobile"),
        )
    report = faq_observation_html(db, "AUD-FAQ-SCOPE")
    assert "Snapshot IDs ausentes ou duplicados: N/D" in report
    assert "Foram identificados" not in report

"""Exercise the real shared materializer, including artifact dependency freshness."""
import sqlite3

from rasai.catalog_report_site import materialize_catalog_report_site, catalog_report_is_fresh
from rasai.contextual_advisory_html import PAGES
from tests.test_catalog_report_site import _workspace, AUDIT_ID


def test_all_seven_existing_pages_get_contextual_projection_and_capture_dependency(tmp_path):
    workspace, _ = _workspace(tmp_path)
    database = workspace.root / "audit.db"
    artifacts = workspace.root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "contextual.html").write_text('<main><details><summary>Qual prazo?</summary></details>'
        '<a href="/terms.pdf">Regulamento privado</a></main>', encoding="utf-8")
    with sqlite3.connect(database) as con:
        con.executescript("""
            CREATE TABLE pages (page_id TEXT, audit_id TEXT);
            ALTER TABLE audit_execution_configurations ADD COLUMN configuration_kind TEXT DEFAULT 'EXECUTION';
            ALTER TABLE audit_execution_configurations ADD COLUMN schema_version TEXT DEFAULT 'LEGACY';
            CREATE TABLE page_snapshots (snapshot_id TEXT, page_id TEXT, device TEXT,
              requested_url TEXT, final_url TEXT, captured_at TEXT, raw_artifact_ref TEXT,
              rendered_artifact_ref TEXT, main_content_ref TEXT);
            ALTER TABLE page_snapshots ADD COLUMN browser_metadata TEXT DEFAULT '{}';
        """)
        page = "PGE-context"
        con.execute("INSERT INTO pages VALUES (?,?)", (page, AUDIT_ID))
        con.execute("INSERT INTO page_snapshots (snapshot_id,page_id,device,requested_url,final_url,captured_at,raw_artifact_ref,rendered_artifact_ref,main_content_ref) VALUES (?,?,?,?,?,?,?,?,?)", (
            "SNP-context", page, "DESKTOP", "https://example.test/", "https://example.test/",
            "2026-09-15T20:00:00Z", "artifacts/contextual.html", None, None))
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    for name in PAGES:
        html = (report / name).read_text(encoding="utf-8")
        assert "id='contextual-content'" in html
        assert "Regulamento privado" not in html
    assert "FAQ - pergunta" in (report / "cat-03.html").read_text(encoding="utf-8")
    assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace, report_dir=report)
    (artifacts / "contextual.html").write_text('<main><p>Outra captura</p></main>')
    assert not catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace, report_dir=report)

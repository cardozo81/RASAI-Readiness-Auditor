"""Exercise the real shared materializer, including artifact dependency freshness."""
import sqlite3

from rasai.catalog_report_site import materialize_catalog_report_site, catalog_report_is_fresh
from rasai.contextual_advisory_html import PAGES
from tests.test_catalog_report_site import _workspace, AUDIT_ID


def _captured_workspace(tmp_path):
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
    return workspace


def test_all_seven_existing_pages_get_contextual_projection_and_capture_dependency(tmp_path):
    workspace = _captured_workspace(tmp_path)
    artifacts = workspace.root / "artifacts"
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    for name in PAGES:
        html = (report / name).read_text(encoding="utf-8")
        assert "id='contextual-content'" in html
        assert "Regulamento privado" not in html
    assert "FAQ - pergunta" in (report / "cat-03.html").read_text(encoding="utf-8")
    assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace, report_dir=report)
    (artifacts / "contextual.html").write_text('<main><p>Outra captura</p></main>')
    assert not catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace, report_dir=report)


def test_v2_additive_materialization_preserves_all_original_blocks_scores_and_navigation(tmp_path, monkeypatch):
    from html.parser import HTMLParser
    from rasai import contextual_advisory_html as panels
    from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
    from rasai.contextual_documents import digest

    class OutsideContext(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth, self.tokens = 0, []

        def handle_starttag(self, tag, attrs):
            if self.depth or dict(attrs).get("id") in {"contextual-content", "contextual-semantic-v2", "contextual-qualification"}:
                if tag not in {"meta", "link", "br", "hr", "img", "input", "source", "wbr"}:
                    self.depth += 1
            else:
                self.tokens.append((tag, attrs))

        def handle_endtag(self, tag):
            if self.depth:
                self.depth -= 1
            else:
                self.tokens.append(("/" + tag,))

        def handle_data(self, data):
            if not self.depth:
                self.tokens.append(("data", data))

    workspace = _captured_workspace(tmp_path)
    database_hash = digest(workspace.database.read_bytes())
    with sqlite3.connect(workspace.database) as con:
        scores = con.execute("SELECT * FROM scores").fetchall()
    with monkeypatch.context() as previous_projection:
        previous_projection.setattr(panels, "contextual_panel", panels._v1_panel)
        baseline_dir = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
        baseline = {p.filename: (baseline_dir / p.filename).read_text(encoding="utf-8") for p in CATALOG_REPORT_PAGES}
    candidate_dir = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    for page in CATALOG_REPORT_PAGES:
        if page.filename == "geo-content-review.html":
            # This route has no legacy counterpart; only existing 20 pages
            # are subject to the byte/DOM-preservation contract.
            continue
        previous, candidate = OutsideContext(), OutsideContext()
        previous.feed(baseline[page.filename])
        current = (candidate_dir / page.filename).read_text(encoding="utf-8")
        candidate.feed(current)
        assert previous.tokens == candidate.tokens, page.filename
        if page.filename in PAGES:
            assert "id='contextual-semantic-v2'" in current
            assert "id='contextual-content'" in current
    assert digest(workspace.database.read_bytes()) == database_hash
    with sqlite3.connect(workspace.database) as con:
        assert con.execute("SELECT * FROM scores").fetchall() == scores

def test_reverse_review_is_21st_page_with_no_private_literal(tmp_path):
    from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
    assert len(CATALOG_REPORT_PAGES) == 21
    assert len({p.filename for p in CATALOG_REPORT_PAGES}) == 21
    workspace = _captured_workspace(tmp_path)
    report_dir = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    review = (report_dir / "geo-content-review.html").read_text(encoding="utf-8")
    assert "id='faq-aria-review'" in review
    assert "id='editorial-ideas'" in review
    assert "Regulamento privado" not in review
    index = (report_dir / "index.html").read_text(encoding="utf-8")
    assert "href='geo-content-review.html'" in index
    assert "id='contextual-content'" in (report_dir / "geo.html").read_text(encoding="utf-8")

def test_each_of_21_html_pages_uses_historical_persisted_timezone(tmp_path, monkeypatch):
    import json
    from rasai.audit_configuration_reuse import configuration_hash
    from rasai.catalog_report_contract import CATALOG_REPORT_PAGES

    workspace = _captured_workspace(tmp_path)
    with sqlite3.connect(workspace.database) as connection:
        original = json.loads(connection.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,)).fetchone()[0])
        original["settings"]["presentation"] = {"timezone": "Europe/Berlin"}
        original["settings"]["environment"]["RASAI_PRESENTATION_TIMEZONE"] = "Europe/Berlin"
        connection.execute(
            "UPDATE audit_execution_configurations SET configuration_json=?, configuration_hash=? WHERE audit_id=?",
            (json.dumps(original, ensure_ascii=False), configuration_hash(original), AUDIT_ID))
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "Asia/Tokyo")
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    assert len(CATALOG_REPORT_PAGES) == 21
    for page in CATALOG_REPORT_PAGES:
        html = (report / page.filename).read_text(encoding="utf-8")
        assert "Europe/Berlin" in html, page.filename
        assert "configuração persistida da auditoria" in html, page.filename
        assert "Asia/Tokyo" not in html, page.filename
    assert "15/09/2026 22:00:00 (Europe/Berlin)" in (
        report / "index.html").read_text(encoding="utf-8")
    assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace, report_dir=report)


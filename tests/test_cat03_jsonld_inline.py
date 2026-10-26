"""In CAT-03 the captured JSON-LD itself must be readable without a modal."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.catalog_report_evidence import _semantic_html, _structured_documents_html


AUDIT_ID = "AUD-JSONLD-INLINE"


def _database(root: Path) -> Path:
    database = root / "audit.db"
    with sqlite3.connect(database) as con:
        con.executescript("""
            CREATE TABLE pages (page_id TEXT, audit_id TEXT, normalized_url TEXT);
            CREATE TABLE page_snapshots (
                page_id TEXT, snapshot_id TEXT, device TEXT,
                structured_data_ref TEXT, final_url TEXT, requested_url TEXT
            );
            INSERT INTO pages VALUES ('P1', 'AUD-JSONLD-INLINE', 'https://example.test/produto');
        """)
    return database


def _snapshot(db: Path, sid: str, device: str, ref: str | None) -> None:
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO page_snapshots VALUES ('P1', ?, ?, ?, 'https://example.test/produto', NULL)",
            (sid, device, ref),
        )


def _artifact(root: Path, sid: str, blocks: object) -> str:
    path = root / "artifacts" / sid / "structured_data.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    return path.relative_to(root).as_posix()


def test_cat03_inline_json_is_visible_without_expansion_and_preserves_original(tmp_path: Path):
    db = _database(tmp_path)
    original = {"@context": "https://schema.org", "@type": "Product",
                "name": "Seguro & Proteção", "offers": {"price": "120.00"},
                "description": "<script>alert(1)</script>"}
    ref = _artifact(tmp_path, "S1", [{
        "index": 0, "raw": json.dumps(original), "parsed": original,
        "types": ["Product"], "parse_error": None,
    }])
    _snapshot(db, "S1", "MOBILE", ref)
    before = (tmp_path / ref).read_bytes()
    html = _semantic_html(db, SimpleNamespace(audit_id=AUDIT_ID))
    inline = html.split("Documentos JSON-LD extraídos — visualização direta", 1)[1].split(
        "Validações de dados estruturados", 1,
    )[0]
    assert "<pre class='pre jsonld-captured-json'" in inline
    assert "&quot;@type&quot;: &quot;Product&quot;" in inline
    assert "&quot;name&quot;: &quot;Seguro &amp; Proteção&quot;" in inline
    assert "120.00" in inline and "&lt;script&gt;alert(1)&lt;/script&gt;" in inline
    assert "<script>alert(1)</script>" not in inline
    assert "<details" not in inline and "data-modal-open" not in inline
    assert "https://example.test/produto" in inline and "S1" in inline
    assert f"../{ref}" in inline
    assert (tmp_path / ref).read_bytes() == before


def test_multiple_capture_documents_and_invalid_blocks_are_distinct(tmp_path: Path):
    db = _database(tmp_path)
    desktop = _artifact(tmp_path, "S1", [
        {"index": 0, "raw": '{"@type":"Organization"}',
         "parsed": {"@type": "Organization", "name": "Empresa"},
         "types": ["Organization"], "parse_error": None},
        {"index": 1, "raw": '{"@type":', "parsed": None,
         "types": [], "parse_error": "INVALID_JSON"},
    ])
    mobile = _artifact(tmp_path, "S2", [
        {"index": 0, "raw": '{"@type":"WebPage"}',
         "parsed": {"@type": "WebPage", "name": "Outro"},
         "types": ["WebPage"], "parse_error": None},
    ])
    _snapshot(db, "S1", "DESKTOP", desktop)
    _snapshot(db, "S2", "MOBILE", mobile)
    html = _structured_documents_html(db, SimpleNamespace(audit_id=AUDIT_ID))
    assert html.count("class='page-card jsonld-inline-document'") == 2
    assert "Organization" in html and "WebPage" in html
    assert "INVALID_JSON" in html and "Não interpretado" in html
    assert "S1" in html and "S2" in html


def test_unavailable_and_outside_files_do_not_create_document_content(tmp_path: Path):
    db = _database(tmp_path)
    _snapshot(db, "none", "MOBILE", None)
    _snapshot(db, "bad", "DESKTOP", "../private.json")
    html = _structured_documents_html(db, SimpleNamespace(audit_id=AUDIT_ID))
    assert "Nenhum artefato JSON-LD foi persistido" in html
    assert "fora da auditoria" in html
    assert "Abrir arquivo original" not in html


def test_secret_values_redacted_only_in_report_projection(tmp_path: Path):
    db = _database(tmp_path)
    ref = _artifact(tmp_path, "S1", [{
        "index": 0, "parsed": {"@type": "Product", "name": "Público",
                               "api_key": "synthetic_test_password"},
        "raw": "raw", "parse_error": None, "types": ["Product"],
    }])
    _snapshot(db, "S1", "MOBILE", ref)
    html = _structured_documents_html(db, SimpleNamespace(audit_id=AUDIT_ID))
    assert "&quot;api_key&quot;: &quot;[REDACTED]&quot;" in html
    assert "synthetic_test_password" not in html
    assert "Público" in html
    assert "synthetic_test_password" in (tmp_path / ref).read_text(encoding="utf-8")


def test_large_file_displays_size_limit_and_original_reference(tmp_path: Path):
    db = _database(tmp_path)
    ref = _artifact(tmp_path, "S1", [{
        "index": 0, "parsed": {"@type": "Article", "name": "A" * (1024 * 1024)},
        "parse_error": None, "types": ["Article"],
    }])
    _snapshot(db, "S1", "MOBILE", ref)
    html = _structured_documents_html(db, SimpleNamespace(audit_id=AUDIT_ID))
    assert "Documento acima de 1 MiB" in html
    assert "Abrir arquivo original" in html
    assert "A" * 1000 not in html

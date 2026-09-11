from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.ai_efficiency_policy import TOKEN_ECONOMY_INSTRUCTION, install as install_ai_efficiency
from rasai.context_reporting import write_context_report
from rasai.context_scope import ContextScope, evidence_scope
from rasai.report_contract import surface_by_filename
from rasai.semantic import OpenAIProvider, SemanticInput


def test_scope_is_derived_from_persisted_identity() -> None:
    assert evidence_scope(page_id=None, snapshot_id=None, device=None) is ContextScope.ORIGIN
    assert evidence_scope(page_id="P1", snapshot_id=None, device=None) is ContextScope.URL
    assert evidence_scope(page_id="P1", snapshot_id="S1", device="MOBILE") is ContextScope.DEVICE_SNAPSHOT


def test_domain_report_is_the_canonical_origin_surface() -> None:
    surface = surface_by_filename("crawling-discovery.html")
    assert surface.label == "Domínio e descoberta"
    assert "robots.txt" in surface.inputs
    assert "sitemaps" in surface.inputs


def test_grouped_report_menu_contrast_is_scoped_to_navigation_details() -> None:
    from rasai.context_scope_runtime import _NAV_GROUP_DETAILS_STYLE, _NAV_GROUP_SUMMARY_STYLE

    assert "background:#364359" in _NAV_GROUP_DETAILS_STYLE
    assert "border:1px solid rgba(255,255,255,.10)" in _NAV_GROUP_DETAILS_STYLE
    assert "color:#d9e2ee" in _NAV_GROUP_SUMMARY_STYLE
    assert "background:#3b4860" in _NAV_GROUP_SUMMARY_STYLE
    assert "opacity:1" in _NAV_GROUP_SUMMARY_STYLE


def test_ai_policy_keeps_one_structured_request_concise() -> None:
    install_ai_efficiency()
    provider = OpenAIProvider(model="test-model", api_key="test-key", transport=lambda *_: {})
    semantic_input = SemanticInput(
        snapshot_id="S1",
        page_url="https://example.test/",
        title="Example",
        main_content="content",
        structured_data={},
        primary_language="pt-BR",
        market="BR",
        evidence=(),
    )
    payload = provider._request_payload(semantic_input)
    assert TOKEN_ECONOMY_INSTRUCTION in payload["instructions"]
    assert len(payload["input"]) == 1


def test_context_report_distinguishes_device_document_variance_without_repeating_origin_detail(tmp_path: Path) -> None:
    root = tmp_path / "AUD-CONTEXT"
    report = root / "report"
    (report / "css").mkdir(parents=True)
    (report / "css" / "site.css").write_text("body{}", encoding="utf-8")
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_targets(audit_id TEXT,input_url TEXT,normalized_origin TEXT);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE evidence(
                evidence_id TEXT PRIMARY KEY,audit_id TEXT,page_id TEXT,snapshot_id TEXT,
                device TEXT,evidence_type TEXT,source TEXT
            );
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,requested_url TEXT,
                browser_metadata TEXT
            );
            CREATE TABLE m24_runs(audit_id TEXT,llms_state TEXT);
            INSERT INTO audit_targets VALUES ('AUD-CONTEXT','https://example.test/','https://example.test');
            INSERT INTO pages VALUES ('P1','AUD-CONTEXT','https://example.test/a');
            INSERT INTO evidence VALUES ('E1','AUD-CONTEXT',NULL,NULL,NULL,'ROBOTS_RULE','https://example.test/robots.txt');
            INSERT INTO evidence VALUES ('E2','AUD-CONTEXT','P1',NULL,NULL,'HTTP_RESPONSE','http');
            INSERT INTO m24_runs VALUES ('AUD-CONTEXT','ABSENT');
            """
        )
        mobile = {
            "context_scope_contract": "CONTEXT-SCOPE-001",
            "document_source": {"sha256": "a" * 64, "bytes": 100},
            "runtime_diagnostics": {"count": 1, "items": [{"type": "PAGE_ERROR", "message": "boom"}]},
        }
        desktop = {
            "context_scope_contract": "CONTEXT-SCOPE-001",
            "document_source": {"sha256": "b" * 64, "bytes": 110},
            "runtime_diagnostics": {"count": 0, "items": []},
        }
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?)",
            ("S-M", "P1", "MOBILE", "https://example.test/a", json.dumps(mobile)),
        )
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?)",
            ("S-D", "P1", "DESKTOP", "https://example.test/a", json.dumps(desktop)),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(root=root, database=database)
    output = write_context_report(audit_id="AUD-CONTEXT", workspace=workspace)
    html = output.read_text(encoding="utf-8")
    assert "Documento recebido varia por dispositivo" in html
    assert "PAGE_ERROR" in html
    assert "Domínio e descoberta" in html
    assert "crawling-discovery.html" in html
    assert "https://example.test/robots.txt" not in html
    assert "não altera fórmulas" in html

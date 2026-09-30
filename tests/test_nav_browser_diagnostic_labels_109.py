"""Focused regression of CAT-06 browser diagnostic event presentation (#109)."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai import catalog_report_adherence as adherence
from rasai import catalog_report_analysis as analysis
from rasai import catalog_report_page as page
from rasai.report_presentation import humanize_report_html


def test_typed_event_name_is_public_and_original_payload_is_immutable() -> None:
    raw = {"events": [
        {"type": "SHARED_ACQUISITION", "message": "SYN-SAMPLE-1", "url": "https://example.test/"},
        {"type": "BRAND_NEW_EVENT_2099", "message": "unchanged"},
    ]}
    current = analysis._browser_diagnostics_public(raw)
    assert current["events"][0] == {
        "type": "Aquisição compartilhada",
        "message": "SYN-SAMPLE-1",
        "url": "https://example.test/",
    }
    assert current["events"][1]["type"] == "Condição técnica não catalogada"
    assert raw["events"][0]["type"] == "SHARED_ACQUISITION"
    assert raw["events"][1]["type"] == "BRAND_NEW_EVENT_2099"


def test_effective_nav_report_preserves_event_evidence_without_generic_type(
    tmp_path, monkeypatch,
) -> None:
    database = tmp_path / "audit.db"
    original = json.dumps({"events": [{
        "type": "SHARED_ACQUISITION",
        "message": "SYN-1",
        "url": "https://example.test/",
    }]})
    con = sqlite3.connect(database)
    con.execute(
        """CREATE TABLE synthetic_apdex_samples (
           audit_id TEXT,sample_id TEXT,run_index INTEGER,captured_at TEXT,
           url TEXT,final_url TEXT,device TEXT,classification TEXT,
           duration_ms REAL,status TEXT,http_status INTEGER,profile_id TEXT,
           cache_policy TEXT,error_message TEXT,error_code TEXT,
           browser_diagnostics TEXT
        )"""
    )
    con.execute(
        """INSERT INTO synthetic_apdex_samples VALUES (
           'AUD-NAV', 'SYN-1', 1, '2026-09-30T15:00:00Z',
           'https://example.test/', 'https://example.test/', 'MOBILE',
           'SATISFIED', 500, 'SUCCESS', 200, 'MOBILE', 'COLD',
           NULL,NULL,?
        )""", (original,),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(page, "_apdex_samples_html", analysis._apdex_samples_html)
    adherence._install_apdex_projection()
    data = SimpleNamespace(audit_id="AUD-NAV")
    html = humanize_report_html(
        page._apdex_samples_html(database, data, experience=False),
        page_name="cat-06.html",
    )
    assert "Aquisição compartilhada" in html
    assert "SYN-1" in html
    assert "https://example.test/" in html
    assert "SHARED_ACQUISITION" not in html
    assert "Condição técnica não catalogada" not in html
    # No mutation: raw diagnostic type still exists in stored evidence.
    con = sqlite3.connect(database)
    try:
        assert json.loads(con.execute(
            "SELECT browser_diagnostics FROM synthetic_apdex_samples"
        ).fetchone()[0])["events"][0]["type"] == "SHARED_ACQUISITION"
    finally:
        con.close()

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.error import HTTPError
import io

from rasai.m18_ai import ProviderErrorClass, ProviderState, RuntimeProviderState
from rasai.m24_ai import _candidates, _configured_provider_state
from rasai.provider_extensions import GeminiProvider, _diagnostic_from_http, gemini_wire_schema
from rasai.report_navigation import _enhance_configuration_accordions
from rasai.report_consistency_v2 import _contexts
from rasai.persistence import AuditWorkspace


def test_gemini_http_400_invalid_request_is_contract_integration_error() -> None:
    body = io.BytesIO(json.dumps({"error": {"code": "invalid_request", "type": "invalid_request"}}).encode())
    exc = HTTPError("https://example.invalid", 400, "bad", {}, body)
    diagnostic = _diagnostic_from_http(exc)
    assert diagnostic.error_class is ProviderErrorClass.CONTRACT_ERROR
    assert diagnostic.http_status == 400
    assert diagnostic.error_code == "invalid_request"


def test_gemini_wire_schema_removes_unsupported_keywords_but_preserves_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 50},
            "items": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        },
        "required": ["name", "items"],
        "additionalProperties": False,
    }
    projected = gemini_wire_schema(schema)
    assert set(projected["properties"]) == {"name", "items"}
    assert "minLength" not in projected["properties"]["name"]
    assert "uniqueItems" not in projected["properties"]["items"]
    assert projected["required"] == ["name", "items"]


def test_m24_recognizes_configured_gemini_and_distinguishes_quarantine() -> None:
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="test-key", transport=lambda *_: {})
    assert _candidates(provider) == (provider,)
    provider._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
    assert _candidates(provider) == ()
    assert _configured_provider_state(provider) == "QUARANTINED_FOR_AUDIT"


def test_configuration_panels_become_closed_vertical_accordions() -> None:
    html = """<section class='panel'><h2>Configuração utilizada neste AUD</h2><div class='grid'>
    <article class='ref-card'><h3>Auditoria</h3><p>Max pages 1</p></article>
    <article class='ref-card'><h3>IA semântica</h3><p>Gemini</p></article>
    <article class='ref-card'><h3>Web Performance</h3><p>auto</p></article>
    </div></section>"""
    result = _enhance_configuration_accordions(html)
    assert "config-accordion-stack" in result
    assert result.count("<details class='config-accordion'>") == 3
    assert "<details class='config-accordion' open" not in result


def test_crux_embedded_in_pagespeed_is_reported_as_direct_api_not_needed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = AuditWorkspace(Path(tmp) / "AUD-X")
        workspace.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(workspace.database)
        db.executescript("""
        CREATE TABLE web_performance_runs(audit_id TEXT, enabled INTEGER, status TEXT, field_source TEXT, categories TEXT);
        CREATE TABLE pages(page_id TEXT, audit_id TEXT, normalized_url TEXT);
        CREATE TABLE web_performance_observations(
          observation_id TEXT,audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,normalized_url TEXT,
          accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT
        );
        CREATE TABLE web_performance_attempts(
          audit_id TEXT,page_id TEXT,snapshot_id TEXT,service TEXT,status TEXT,http_status INTEGER,error_code TEXT,error_message TEXT,created_at TEXT,attempt_id TEXT
        );
        """)
        db.execute("INSERT INTO web_performance_runs VALUES (?,?,?,?,?)", ("AUD-X",1,"SUCCESS","auto",json.dumps(["accessibility"])))
        db.execute("INSERT INTO pages VALUES (?,?,?)", ("P1","AUD-X","https://example.com/"))
        db.execute("INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?)", ("O1","AUD-X","P1","S1","MOBILE","https://example.com/",90,"artifact.json",None,"PAGESPEED_CRUX"))
        db.execute("INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?,?,?)", ("AUD-X","P1","S1","PAGESPEED_INSIGHTS","SUCCESS",200,None,None,"2026-01-01","A1"))
        db.commit(); db.close()
        contexts = _contexts("AUD-X", workspace)
        assert len(contexts) == 1
        assert contexts[0].crux_status == "NÃO NECESSÁRIO"
        assert "própria resposta PageSpeed" in contexts[0].crux_reason

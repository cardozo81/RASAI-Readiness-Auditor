from __future__ import annotations

from types import SimpleNamespace

from rasai.execution_consistency_runtime import _consistent_standards_summary
from rasai.standards_metrics import _normalize_w3c_messages


def test_html_validator_messages_are_bounded_and_preserve_location_and_extract() -> None:
    rows = _normalize_w3c_messages([
        {
            "type": "error",
            "message": "Element h4 not allowed as child of element div in this context.",
            "extract": "<div><h4>Title</h4></div>",
            "firstLine": 31,
            "firstColumn": 9,
        },
        {"type": "info", "subtype": "warning", "message": "Consider adding a lang attribute."},
        {"type": "info", "message": "not a warning"},
    ])
    assert len(rows) == 2
    assert rows[0]["first_line"] == 31
    assert rows[0]["first_column"] == 9
    assert "<h4>" in rows[0]["extract"]
    assert rows[1]["subtype"] == "warning"


def test_cat03_w3c_projection_explains_approval_and_correction(tmp_path) -> None:
    import json
    import sqlite3

    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE standards_metric_observations(
                audit_id TEXT, metric_id TEXT, label TEXT, state TEXT, value REAL, unit TEXT,
                target TEXT, source TEXT, methodology TEXT, details_json TEXT
            );
            CREATE TABLE standards_service_runs(
                audit_id TEXT, service_id TEXT, state TEXT, targets_attempted INTEGER,
                targets_succeeded INTEGER, details_json TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO standards_metric_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "AUD", "w3c_html_conformance", "W3C HTML Conformance", "FAIL", 1, "error_count",
                "https://example.test/", "W3C Nu HTML Checker", "W3C Nu Checker out=json outcome",
                json.dumps({
                    "errors": 1,
                    "non_document_errors": 0,
                    "messages": [{
                        "type": "error",
                        "message": "Element h4 not allowed as child of element div in this context.",
                        "extract": "<div><h4>Title</h4></div>",
                        "first_line": 31,
                        "first_column": 9,
                    }],
                }),
            ),
        )
        con.commit()
    finally:
        con.close()

    html = _consistent_standards_summary(database, SimpleNamespace(audit_id="AUD"))
    assert "Ver erros e correção" in html
    assert "Aprovado quando o W3C Nu Checker retornar 0 erros HTML" in html
    assert "Linha 31, coluna 9" in html
    assert "Element h4 not allowed" in html
    assert "Reposicionar ou substituir o elemento" in html

def test_w3c_summary_links_to_cat09_remediation_anchor(tmp_path) -> None:
    import json
    import sqlite3

    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE standards_metric_observations(
                audit_id TEXT, metric_id TEXT, label TEXT, state TEXT, value REAL, unit TEXT,
                target TEXT, source TEXT, methodology TEXT, details_json TEXT
            );
            CREATE TABLE standards_service_runs(
                audit_id TEXT, service_id TEXT, state TEXT, targets_attempted INTEGER,
                targets_succeeded INTEGER, details_json TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO standards_metric_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "AUD", "w3c_html_conformance", "W3C HTML Conformance", "FAIL", 1,
                "error_count", "https://example.test/", "W3C Nu HTML Checker",
                "W3C Nu Checker out=json outcome",
                json.dumps({"errors": 1, "messages": []}),
            ),
        )
        con.commit()
    finally:
        con.close()

    html = _consistent_standards_summary(database, SimpleNamespace(audit_id="AUD"))
    assert "cat-09.html#w3c-remediation" in html
    assert "Ver remediações no CAT-09" in html

def test_final_post_smoke_w3c_owner_links_to_cat09(tmp_path) -> None:
    import json
    import sqlite3
    from rasai.post_smoke_alignment import _standards_summary

    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE standards_metric_observations(
                audit_id TEXT, metric_id TEXT, label TEXT, state TEXT, value REAL, unit TEXT,
                target TEXT, source TEXT, methodology TEXT, details_json TEXT
            );
            CREATE TABLE standards_service_runs(
                audit_id TEXT, service_id TEXT, state TEXT, targets_attempted INTEGER,
                targets_succeeded INTEGER, details_json TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO standards_metric_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "AUD", "w3c_html_conformance", "W3C HTML Conformance", "FAIL", 1,
                "error_count", "https://example.test/", "W3C Nu HTML Checker",
                "W3C Nu Checker out=json outcome",
                json.dumps({"errors": 1, "messages": []}),
            ),
        )
        con.commit()
    finally:
        con.close()

    html = _standards_summary(database, SimpleNamespace(audit_id="AUD"))
    assert "cat-09.html#w3c-remediation" in html
    assert "Ver remediações no CAT-09" in html

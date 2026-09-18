from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.accepted_audit_refinements import _remediation_html, _w3c_remediation_html
from rasai import catalog_report_analysis as analysis


def _database(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE standards_metric_observations(
                audit_id TEXT, metric_id TEXT, state TEXT, value REAL, unit TEXT,
                target TEXT, source TEXT, methodology TEXT, details_json TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO standards_metric_observations VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    "AUD", "w3c_html_conformance", "FAIL", 1, "error_count",
                    "https://example.test/", "W3C Nu HTML Checker",
                    "W3C Nu Checker out=json outcome",
                    json.dumps({
                        "messages": [{
                            "type": "error",
                            "message": "Element h4 not allowed as child of element div in this context.",
                            "extract": "<div><h4>Title</h4></div>",
                            "first_line": 31,
                            "first_column": 9,
                        }]
                    }),
                ),
                (
                    "AUD", "w3c_css_conformance", "FAIL", 1, "error_count",
                    "https://example.test/", "W3C CSS Validation Service",
                    "W3C CSS validator SOAP outcome",
                    json.dumps({
                        "error_details": [{
                            "line": 17,
                            "message": "Parse Error",
                            "context": ".hero { color: #12; }",
                            "type": "parse-error",
                        }]
                    }),
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_cat09_projects_w3c_failures_as_deterministic_remediation(tmp_path) -> None:
    database = tmp_path / "audit.db"
    _database(database)

    rows, modals = _w3c_remediation_html(database, "AUD", analysis)
    html = "".join(modals)

    assert len(rows) == 2
    assert "Corrigir Conformidade HTML W3C" in str(rows)
    assert "Corrigir Conformidade CSS W3C" in str(rows)
    assert "CAT-01 - padrões e validação W3C" in str(rows)
    assert "Linha 31, coluna 9" in html
    assert "Element h4 not allowed" in html
    assert "Reposicionar ou substituir o elemento" in html
    assert "Linha 17" in html
    assert "Parse Error" in html
    assert "Corrigir a sintaxe da declaração" in html
    assert "Não é inferência da IA" in html
    assert "Critério de aceite" in html


def test_cat09_does_not_invent_details_when_only_w3c_count_was_persisted(tmp_path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE standards_metric_observations(
                audit_id TEXT, metric_id TEXT, state TEXT, value REAL, unit TEXT,
                target TEXT, source TEXT, methodology TEXT, details_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO standards_metric_observations VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "AUD", "w3c_html_conformance", "FAIL", 9, "error_count",
                "https://example.test/", "W3C Nu HTML Checker",
                "W3C Nu Checker out=json outcome", json.dumps({"errors": 9}),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    rows, modals = _w3c_remediation_html(database, "AUD", analysis)
    assert len(rows) == 1
    html = "".join(modals)
    assert "Detalhe individual não materializado nesta AUD" in html
    assert "9" in html

def test_cat09_remediation_exposes_stable_w3c_anchor(tmp_path) -> None:
    database = tmp_path / "audit.db"
    _database(database)

    html = _remediation_html(database, SimpleNamespace(audit_id="AUD"))
    assert "id='w3c-remediation'" in html
    assert "Corrigir Conformidade HTML W3C" in html
    assert "Corrigir Conformidade CSS W3C" in html

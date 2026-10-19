"""Cross-catalog decision evidence matrix, no new audit or provider traffic."""
from __future__ import annotations

import json
import sqlite3

from rasai.report_decision_matrix import (
    decision_evidence_matrix, decision_evidence_matrix_html,
)
from rasai.report_decision_matrix_cli import inspect_audit_decision_evidence, main


def _overall(device="MOBILE", coverage=0.974737):
    return {
        "audit_id": "AUD-CROSS-604",
        "dimension": "OVERALL_READINESS",
        "device": device,
        "value": 86.484962,
        "coverage": coverage,
        "confidence": "HIGH",
        "consolidation_status": "CONSOLIDATED",
        "limitations": json.dumps([
            "READINESS_STATUS:ATTENTION",
            "CRITICAL_GATE:DISCOVERY:PASS",
            "CRITICAL_GATE:INDEXABILITY:PASS",
            "CRITICAL_GATE:EXTRACTION:PASS",
        ]),
    }


def _matrix(**extra):
    args = {
        "audit_id": "AUD-CROSS-604",
        "scores": [
            _overall(),
            {"dimension": "CONTENT_VALUE", "device": "MOBILE",
             "coverage": .7, "confidence": "LOW"},
        ],
        "web": {
            "performance_score": 1,
            "field_scope": "ORIGIN",
            "lcp_p75_ms": 4357,
            "inp_p75_ms": 415,
            "cls_p75": .89,
        },
        "catalog_statuses": {"CAT-06": "Parcial", "CAT-07": "Concluído"},
        "serp_depth": (9, 20),
        "optional_seo_discounts": [
            {"version": "SCORE-GEO-004", "rule_id": "BR-GEO-017"},
        ],
    }
    args.update(extra)
    return decision_evidence_matrix(**args)


def test_604_actual_style_facts_have_separate_scope_and_never_become_new_score():
    result = _matrix()
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["audit_id"] == "AUD-CROSS-604"
    assert result["non_additive"] is True
    assert result["audit_writes"] == result["provider_requests"] == 0
    rows = {row["indicator"]: row for row in result["rows"]}
    assert rows["SARI / MOBILE"]["observed"] == "86,5 / 100"
    assert "97,5% (fração 0.974737)" in rows["SARI / MOBILE"]["limitation"]
    assert rows["Lighthouse / desempenho"]["observed"] == "1,0 / 100"
    assert "Origem agregada" in rows["Core Web Vitals / CrUX"]["scope"]
    assert "4357ms" in rows["Core Web Vitals / CrUX"]["observed"]
    assert rows["SERP / profundidade"]["observed"] == "9 / 20 posições"
    assert rows["Apdex de navegação"]["observed"] == "Parcial"
    assert rows["Sinais SEO opcionais"]["observed"] == "1 contribuição(ões)"
    assert rows["Validação externa de alegações comerciais"]["observed"] == (
        "Não atestada por esta matriz"
    )
    assert rows["Presença / citação generativa"]["observed"] == "N/D"
    rendered = decision_evidence_matrix_html(result)
    assert "Matriz" not in rendered  # the section title belongs to the caller
    assert "Escopo físico" in rendered
    assert "<code>scores.OVERALL_READINESS</code>" in rendered
    assert "não comprova" in rendered.lower()
    assert "não equivalem a zero" in rendered


def test_604_does_not_present_missing_invalid_scope_or_coverage_as_real():
    invalids = _matrix(
        scores=[_overall(coverage=True)],
        web={"performance_score": float("inf"), "field_scope": "UNKNOWN",
             "lcp_p75_ms": 2500},
        serp_depth=None,
        optional_seo_discounts=[],
    )
    rows = {row["indicator"]: row for row in invalids["rows"]}
    assert "N/D" in rows["SARI / MOBILE"]["limitation"]
    assert rows["Lighthouse / desempenho"]["observed"] == "N/D"
    assert rows["Core Web Vitals / CrUX"]["scope"] == "Escopo de campo não comprovado"
    assert "SERP / profundidade" not in rows
    assert "Sinais SEO opcionais" not in rows
    assert _matrix(scores=[_overall(), _overall()])["status"] == "NOT_VERIFIABLE"
    assert decision_evidence_matrix_html(
        _matrix(scores=[_overall(), _overall()])
    ) == "<div class='notice'>Reconciliação de evidências: N/D.</div>"
    assert decision_evidence_matrix(audit_id="", scores=[])["status"] == "NOT_VERIFIABLE"


def test_604_escapes_literal_evidence_and_refuses_inconsistent_projection():
    data = _matrix(
        web={"performance_score": 7, "field_scope": "<img src=x onerror=alert(1)>",
             "lcp_p75_ms": 1000},
    )
    data["rows"][0]["indicator"] = "<script>alert('X')</script>"
    rendered = decision_evidence_matrix_html(data)
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "Não atestada por esta matriz" in rendered


def test_604_cli_reads_only_sealed_existing_aud_and_never_creates_database(
    tmp_path, capsys,
):
    aud = tmp_path / "AUD-CROSS-604"
    aud.mkdir()
    source = aud / "audit.db"
    assert inspect_audit_decision_evidence(aud)["status"] == "NOT_VERIFIABLE"
    assert not source.exists()
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE audits(audit_id TEXT)")
        con.execute("INSERT INTO audits VALUES('AUD-CROSS-604')")
        con.execute(
            "CREATE TABLE scores("
            "audit_id TEXT,dimension TEXT,device TEXT,value REAL,"
            "coverage REAL,confidence TEXT,consolidation_status TEXT,"
            "limitations TEXT)"
        )
        con.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?)",
            (
                "AUD-CROSS-604", "OVERALL_READINESS", "MOBILE",
                86.484962, .974737, "HIGH", "CONSOLIDATED",
                _overall()["limitations"],
            ),
        )
        con.execute(
            "CREATE TABLE web_performance_observations("
            "audit_id TEXT,performance_score REAL,field_scope TEXT,lcp_p75_ms REAL)"
        )
        con.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?)",
            ("AUD-CROSS-604", 1.0, "ORIGIN", 4357),
        )
    original = source.read_bytes()
    projected = inspect_audit_decision_evidence(aud)
    assert projected["status"] == "DESCRIPTIVE_ONLY"
    assert projected["provider_requests"] == 0
    assert projected["audit_writes"] == 0
    assert projected["rows"][0]["observed"] == "86,5 / 100"
    indicators = {row["indicator"]: row for row in projected["rows"]}
    assert indicators["Apdex de navegação"]["observed"] == "INDETERMINADO"
    assert indicators["Apdex de experiência"]["observed"] == "INDETERMINADO"
    assert main([str(aud)]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["status"] == "DESCRIPTIVE_ONLY"
    assert source.read_bytes() == original
    (tmp_path / "AUD-CROSS-604" / "audit.db-wal").write_bytes(b"pending")
    assert inspect_audit_decision_evidence(aud)["status"] == "NOT_VERIFIABLE"
    assert main([str(aud)]) == 2
    assert "NOT_VERIFIABLE" in capsys.readouterr().out
    assert source.read_bytes() == original

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai.accepted_audit_refinements import (
    _improvement_html,
    _repair_scope_findings,
)
from rasai.improvement_intelligence import (
    _required_actionable_recommendation_finding_ids,
)


def test_high_lighthouse_accessibility_finding_is_required_for_deep_guidance() -> None:
    findings=[
        {"finding_id":"F-CONTRAST","source":"LIGHTHOUSE","domain":"ACCESSIBILITY","severity":"HIGH"},
        {"finding_id":"F-PERF","source":"LIGHTHOUSE","domain":"PERFORMANCE","severity":"HIGH"},
        {"finding_id":"F-LOW","source":"LIGHTHOUSE","domain":"ACCESSIBILITY","severity":"LOW"},
    ]
    assert _required_actionable_recommendation_finding_ids(findings)==["F-CONTRAST"]


def test_missing_actionable_accessibility_finding_enters_repair_scope() -> None:
    findings=[
        {"finding_id":"F-CONTRAST","source":"LIGHTHOUSE","domain":"ACCESSIBILITY","severity":"HIGH"},
        {"finding_id":"OTHER","source":"HTML_STRUCTURE","domain":"TECHNICAL_HTML","severity":"HIGH"},
    ]
    scope=_repair_scope_findings(findings,[],[])
    assert [item["finding_id"] for item in scope]==["F-CONTRAST"]


def test_cat08_problem_modal_exposes_ai_example_and_verification(tmp_path) -> None:
    database=tmp_path/"audit.db"
    con=sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE improvement_intelligence_runs(
                audit_id TEXT,status TEXT,analysis_language TEXT,max_recommendations INTEGER,ai_summary TEXT
            );
            CREATE TABLE improvement_intelligence_findings(
                audit_id TEXT,finding_id TEXT,title TEXT,observation TEXT,domain TEXT,severity TEXT,
                source TEXT,selector TEXT,original_html TEXT,evidence_ids_json TEXT
            );
            CREATE TABLE improvement_intelligence_recommendations(
                audit_id TEXT,finding_id TEXT,title TEXT,recommendation TEXT,rationale TEXT,
                domain TEXT,severity TEXT,priority TEXT,confidence REAL,selector TEXT,
                suggested_html TEXT,suggested_text TEXT,verification TEXT
            );
            """
        )
        con.execute("INSERT INTO improvement_intelligence_runs VALUES (?,?,?,?,?)",("AUD","COMPLETE","pt-BR",30,"ok"))
        con.execute(
            "INSERT INTO improvement_intelligence_findings VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("AUD","F-CONTRAST","Low-contrast text is difficult or impossible for many users to read.",
             "Low-contrast text is difficult or impossible for many users to read.",
             "ACCESSIBILITY","HIGH","LIGHTHOUSE",".banner","<p class='banner'>Texto</p>","[]"),
        )
        con.execute(
            "INSERT INTO improvement_intelligence_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AUD","F-CONTRAST","Corrigir contraste","Aumentar a relação de contraste entre texto e fundo.",
             "O contraste atual dificulta a leitura.","ACCESSIBILITY","HIGH","HIGH",0.92,".banner",
             "<style>.banner{color:#1f2937;background:#fff}</style>",None,
             "Reexecutar Lighthouse e confirmar contraste WCAG sem falha."),
        )
        con.commit()
    finally:
        con.close()

    html=_improvement_html(database,SimpleNamespace(audit_id="AUD"))
    assert "Contraste insuficiente entre texto e plano de fundo" in html
    assert "Exemplo técnico sugerido pela IA" in html
    assert ".banner{color:#1f2937;background:#fff}" in html
    assert "Como validar a correção" in html
    assert "Reexecutar Lighthouse" in html

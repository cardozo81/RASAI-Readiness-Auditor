from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai.semantic_coherence_reporting import _auto_interpretation_html


class _Evidence:
    @staticmethod
    def _table(headers, rows, **_kwargs):
        return "|".join(str(value) for row in rows for value in row)

    @staticmethod
    def _kv(items):
        return "|".join(str(value) for item in items for value in item)

    @staticmethod
    def _modal_button(modal_id, label):
        return f"[{label}:{modal_id}]"

    @staticmethod
    def _modal(modal_id, title, context, body):
        return f"<modal id='{modal_id}'>{title}|{context}|{body}</modal>"


def test_cat03_auto_projection_uses_real_canonical_configuration_and_marks_effective_row(tmp_path) -> None:
    database=tmp_path/"audit.db"
    con=sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE content_analysis_contexts(
                audit_id TEXT,risk_profile TEXT,ymyl_category TEXT,page_purpose TEXT,
                intended_audience TEXT,experience_requirement TEXT,freshness_sensitivity TEXT,
                content_origin TEXT
            );
            CREATE TABLE content_context_interpretations(
                interpretation_id TEXT,audit_id TEXT,sequence_no INTEGER,snapshot_id TEXT,page_url TEXT,
                field_name TEXT,status TEXT,interpreted_value TEXT,confidence REAL,rationale TEXT,
                evidence_ids_json TEXT,provider TEXT,model TEXT,interpretation_type TEXT,
                affects_scoring INTEGER,contract_version TEXT,created_at TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO content_analysis_contexts VALUES (?,?,?,?,?,?,?,?)",
            ("AUD","ymyl","auto","product-service","auto","auto","low","first-party"),
        )
        rows=[
            ("I1","AUD",1,"S1","https://example.test/","risk_profile","NOT_REQUESTED",None,1.0,"explicit","[]","OPENAI","m1","AI_INFERENCE",0,"C1","2026-01-01T00:00:00Z"),
            ("I2","AUD",1,"S1","https://example.test/","ymyl_category","INTERPRETED","other-significant-welfare",0.60,"first","[]","OPENAI","m1","AI_INFERENCE",0,"C1","2026-01-01T00:00:01Z"),
            ("I3","AUD",2,"S1","https://example.test/","ymyl_category","INTERPRETED","financial-security",0.96,"effective","[]","DEEPSEEK","m2","AI_INFERENCE",0,"C1","2026-01-01T00:00:02Z"),
        ]
        con.executemany("INSERT INTO content_context_interpretations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)
        con.commit()
    finally:
        con.close()

    html=_auto_interpretation_html(_Evidence,database,"AUD")
    assert "Interpretações de contexto por IA" in html
    assert "Perfil de risco|YMYL (ymyl)|Não solicitado" in html
    assert "Não - campo declarado" in html
    assert "Categoria YMYL|Automático" in html
    assert "Automático (auto)" not in html
    assert "Segurança financeira (financial-security)|Sim" in html
    assert "Outra interpretação automática posterior/efetiva foi selecionada" in html

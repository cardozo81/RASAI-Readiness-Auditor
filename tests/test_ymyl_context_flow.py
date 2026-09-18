from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai import ai_execution_state
from rasai.ai_exchange_log import AiExchangeRecorder, ContextInterpretationRecord
from rasai.editorial_risk_context import build_editorial_risk_context, ymyl_prompt_directive
from rasai.improvement_intelligence import build_improvement_request_context
from rasai.semantic_coherence_reporting import _ymyl_alignment_html


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE content_analysis_contexts(
                audit_id TEXT,
                risk_profile TEXT,
                ymyl_category TEXT,
                page_purpose TEXT,
                intended_audience TEXT,
                experience_requirement TEXT,
                freshness_sensitivity TEXT,
                content_origin TEXT
            );
            CREATE TABLE semantic_coherence_assessments(
                audit_id TEXT,
                criterion_id TEXT,
                snapshot_id TEXT,
                page_url TEXT,
                result TEXT,
                confidence REAL,
                declared_context TEXT,
                observed_context TEXT,
                evidence_ids_json TEXT,
                reasoning_summary TEXT,
                provider TEXT,
                model TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO content_analysis_contexts VALUES (?,?,?,?,?,?,?,?)",
            (
                "AUD-YMYL",
                "ymyl",
                "auto",
                "product-service",
                "auto",
                "auto",
                "high",
                "first-party",
            ),
        )
        connection.execute(
            "INSERT INTO semantic_coherence_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "AUD-YMYL",
                "SC-P12",
                "S1",
                "https://example.test/",
                "PARTIAL",
                0.82,
                "YMYL risk profile",
                "Responsibility is visible but support is incomplete.",
                '["EV-1"]',
                "Trust support is incomplete for the configured risk context.",
                "OPENAI",
                "gpt-test",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return database


def _install_live_category_interpretation() -> None:
    ai_execution_state.clear_current_ai_execution()
    recorder = AiExchangeRecorder()
    recorder._interpretations.append(
        ContextInterpretationRecord(
            sequence_no=2,
            provider="OPENAI",
            model="gpt-test",
            snapshot_id="S1",
            page_url="https://example.test/",
            fields={
                "ymyl_category": {
                    "status": "INTERPRETED",
                    "value": "financial-security",
                    "confidence": 0.91,
                    "rationale": "The page can materially affect a financial decision.",
                    "evidence_ids": ["EV-1"],
                }
            },
        )
    )
    ai_execution_state.set_current_ai_execution("PRIMARY", recorder)


def test_editorial_context_combines_config_live_auto_interpretation_and_sc_p12(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    context = build_editorial_risk_context(
        SimpleNamespace(database=database, root=tmp_path),
        "AUD-YMYL",
        page_url="https://example.test/",
    )
    assert context["ymyl"]["active"] is True
    assert context["ymyl"]["configured_category"] == "auto"
    assert context["ymyl"]["effective_category"] == "financial-security"
    assert context["ymyl"]["alignment_result"] == "PARTIAL"
    assert context["ymyl"]["evidence_ids"] == ["EV-1"]
    assert context["auto_interpretations"]["ymyl_category"]["source"] == "CURRENT_AI_INFERENCE"
    ai_execution_state.clear_current_ai_execution()


def test_improvement_request_carries_same_ymyl_context_and_guardrails(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    target = SimpleNamespace(
        url="https://example.test/",
        input_url="https://example.test/",
        device="DESKTOP",
        market="BR",
        title="Example",
        description="Example description",
        canonical="https://example.test/",
    )
    config = SimpleNamespace(domains=("CONTENT",))
    request, instructions = build_improvement_request_context(
        audit_id="AUD-YMYL",
        workspace=SimpleNamespace(database=database, root=tmp_path),
        context=target,
        config=config,
        findings=[{"finding_id": "F1", "evidence_ids": ["EV-1"]}],
        evidence_context={"semantic": "persisted"},
        language="pt-BR",
    )
    assert request["editorial_risk_context"]["ymyl"]["effective_category"] == "financial-security"
    assert request["governance"]["ymyl_is_context_not_compliance"] is True
    assert "WHERE the gap is" in instructions
    assert "HOW it should be improved" in instructions
    assert "legal/regulatory compliance" in instructions
    ai_execution_state.clear_current_ai_execution()


def test_cat03_exposes_config_interpretation_and_ymyl_alignment(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()

    class Evidence:
        @staticmethod
        def _table(headers, rows, **_kwargs):
            return "|".join(str(value) for row in rows for value in row)

    html = _ymyl_alignment_html(Evidence, database, "AUD-YMYL")
    assert "Contexto YMYL × conteúdo observado" in html
    assert "financial-security" in html
    assert "Aderência parcial" in html
    assert "SC-P12" in html
    assert "não declara conformidade legal" in html
    ai_execution_state.clear_current_ai_execution()


def test_non_ymyl_context_does_not_force_ymyl_recommendations(tmp_path: Path) -> None:
    database = _database(tmp_path)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE content_analysis_contexts SET risk_profile='standard', ymyl_category='none'"
        )
        connection.commit()
    finally:
        connection.close()
    ai_execution_state.clear_current_ai_execution()
    context = build_editorial_risk_context(database, "AUD-YMYL")
    directive = ymyl_prompt_directive(context)
    assert context["ymyl"]["active"] is False
    assert "Do not invent a YMYL classification" in directive

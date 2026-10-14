from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai import ai_execution_state
from rasai.ai_exchange_log import AiExchangeRecorder, ContextInterpretationRecord
from rasai.editorial_risk_context import build_editorial_risk_context, ymyl_prompt_directive
from rasai.improvement_intelligence import (
    _semantic_risk_findings,
    build_improvement_request_context,
)
from rasai.accepted_audit_refinements import (
    _repair_scope_findings,
    _ymyl_analysis_context_html,
)
from rasai.semantic_coherence_reporting import _ymyl_alignment_html
from rasai.faq_observation_601 import faq_observation_html, inspect_faq_html
from rasai import catalog_report_analysis



def test_faq_snapshot_distinguishes_collapsed_unmounted_from_absent_answer() -> None:
    html = (
        '<a role="button" aria-controls="FrequentlyAsked-question1" '
        'aria-expanded="false">Pergunta um</a>'
        '<a role="button" aria-controls="FrequentlyAsked-question2" '
        'aria-expanded="false">Pergunta dois</a>'
        '<div id="FrequentlyAsked-question2">Resposta existente no DOM</div>'
        '<a role="button" aria-controls="OtherAccordion-1" '
        'aria-expanded="false">Plano de cobertura</a>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "collapsed": 2, "unmounted": 1, "mounted": 1,
        "mounted_with_text": 1, "mounted_without_text": 0,
    }



def test_faq_mounted_empty_panel_is_not_called_answered() -> None:
    html = (
        '<button aria-controls="faq-1" aria-expanded="false">Pergunta?</button>'
        '<div id="faq-1"><script>var answer = "not visible"</script>'
        '<span> </span></div>'
        '<button aria-controls="faq-2" aria-expanded="false">Pergunta dois?</button>'
        '<div id="faq-2"><span>Resposta recuperável</span></div>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "collapsed": 2, "unmounted": 0, "mounted": 2,
        "mounted_with_text": 1, "mounted_without_text": 1,
    }



def test_faq_readonly_report_does_not_claim_editorial_absence(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    artifact = tmp_path / "artifacts" / "rendered" / "P1" / "mobile" / "S1.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        '<a role="button" aria-controls="FrequentlyAsked-q1" '
        'aria-expanded="false">Uma pergunta</a>', encoding="utf-8",
    )
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        connection.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT)"
        )
        connection.execute("INSERT INTO pages VALUES('P1','AUD-1')")
        connection.execute(
            "INSERT INTO page_snapshots VALUES(?,?,?)",
            ("S1", "P1", "artifacts/rendered/P1/mobile/S1.html"),
        )
    previous_db = db.read_bytes()
    previous_html = artifact.read_bytes()
    report = faq_observation_html(db, "AUD-1")
    assert "1 painel(is) não estavam presentes no DOM" in report
    assert "não prova ausência editorial" in report
    assert "também não comprova acesso sem interação" in report
    assert "não altera BR-GEO-039, BR-GEO-049" in report
    assert "Proveniência por captura" in report
    assert "<code>S1</code>" in report
    assert "<td>1</td><td>1</td><td>1</td>" in report
    assert db.read_bytes() == previous_db
    assert artifact.read_bytes() == previous_html
    assert faq_observation_html(db, "AUD-OTHER") == ""


def test_faq_diagnostic_rejects_out_of_root_artifact(tmp_path: Path) -> None:
    from rasai.faq_observation_601 import _safe_rendered_file

    outside = tmp_path.parent / "outside-faq.html"
    assert _safe_rendered_file(tmp_path, "../outside-faq.html") is None
    assert _safe_rendered_file(tmp_path, "artifacts/rendered/../outside-faq.html") is None



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
                "low",
                "first-party",
            ),
        )
        rows = [
            (
                "AUD-YMYL", "SC-P11", "S1", "https://example.test/", "PARTIAL", 0.89,
                "YMYL financial-security", "Material claims have limited observable qualification.",
                '["EV-11"]', "Claim support is incomplete for the configured risk context.",
                "OPENAI", "gpt-test",
            ),
            (
                "AUD-YMYL", "SC-P12", "S1", "https://example.test/", "PARTIAL", 0.85,
                "YMYL financial-security", "Organization is identifiable but editorial responsibility is limited.",
                '["EV-12"]', "Responsibility support is incomplete for the configured risk context.",
                "OPENAI", "gpt-test",
            ),
            (
                "AUD-YMYL", "SC-P13", "S1", "https://example.test/", "NOT_DETERMINABLE", 0.94,
                "Low freshness sensitivity", "No sufficient publication/update signals were observed.",
                '["EV-13"]', "Freshness cannot be concluded from the available evidence.",
                "OPENAI", "gpt-test",
            ),
        ]
        connection.executemany(
            "INSERT INTO semantic_coherence_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
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
                    "confidence": 0.96,
                    "rationale": "The page can materially affect a financial decision.",
                    "evidence_ids": ["EV-1"],
                }
            },
        )
    )
    ai_execution_state.set_current_ai_execution("PRIMARY", recorder)


def test_editorial_context_combines_user_config_auto_category_and_all_ymyl_criteria(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    context = build_editorial_risk_context(
        SimpleNamespace(database=database, root=tmp_path),
        "AUD-YMYL",
        page_url="https://example.test/",
    )
    ymyl = context["ymyl"]
    assert ymyl["active"] is True
    assert ymyl["configured_risk_profile"] == "ymyl"
    assert ymyl["configured_category"] == "auto"
    assert ymyl["effective_category"] == "financial-security"
    assert ymyl["alignment_result"] == "PARTIAL"
    assert ymyl["content_change_required"] is True
    assert ymyl["configuration_relation"]["conflict"] is False
    assert "parametrização do usuário foi respeitada" in ymyl["configuration_relation"]["label"]
    assert {item["criterion_id"] for item in ymyl["coherence"]} == {"SC-P11", "SC-P12", "SC-P13"}
    assert set(ymyl["evidence_ids"]) == {"EV-1", "EV-11", "EV-12", "EV-13"}
    ai_execution_state.clear_current_ai_execution()


def test_improvement_request_requires_recommendations_for_actionable_ymyl_findings(tmp_path: Path) -> None:
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
    config = SimpleNamespace(domains=("CONTENT",), max_recommendations=30)
    finding = {
        "finding_id": "SEMANTIC-YMYL:SC-P11:S1",
        "source": "SEMANTIC_COHERENCE_YMYL",
        "evidence_ids": ["EV-11"],
    }
    request, instructions = build_improvement_request_context(
        audit_id="AUD-YMYL",
        workspace=SimpleNamespace(database=database, root=tmp_path),
        context=target,
        config=config,
        findings=[finding],
        evidence_context={"semantic": "persisted"},
        language="pt-BR",
    )
    assert request["editorial_risk_context"]["ymyl"]["effective_category"] == "financial-security"
    assert request["governance"]["required_ymyl_recommendation_finding_ids"] == [
        "SEMANTIC-YMYL:SC-P11:S1"
    ]
    assert "must receive exactly one evidence-bound recommendation" in instructions
    assert "legal/regulatory compliance" in instructions
    assert "hyphen" in instructions.casefold()
    ai_execution_state.clear_current_ai_execution()


def test_missing_required_ymyl_recommendation_is_added_to_repair_scope() -> None:
    findings = [
        {"finding_id": "SEMANTIC-YMYL:SC-P11:S1", "source": "SEMANTIC_COHERENCE_YMYL"},
        {"finding_id": "SEMANTIC-YMYL:SC-P12:S1", "source": "SEMANTIC_COHERENCE_YMYL"},
        {"finding_id": "OTHER", "source": "HTML_STRUCTURE"},
    ]
    accepted = [{"finding_id": "SEMANTIC-YMYL:SC-P12:S1"}]
    scope = _repair_scope_findings(findings, [], accepted)
    assert [item["finding_id"] for item in scope] == ["SEMANTIC-YMYL:SC-P11:S1"]


def test_ymyl_semantic_partial_gaps_become_improvement_findings(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        findings, summary = _semantic_risk_findings(
            connection,
            "AUD-YMYL",
            SimpleNamespace(url="https://example.test/"),
            SimpleNamespace(database=database, root=tmp_path),
        )
    finally:
        connection.close()
    ids = {item["finding_id"] for item in findings}
    assert ids == {"SEMANTIC-YMYL:SC-P11:S1", "SEMANTIC-YMYL:SC-P12:S1"}
    assert summary["active"] is True
    assert all(item["source"] == "SEMANTIC_COHERENCE_YMYL" for item in findings)
    ai_execution_state.clear_current_ai_execution()


def test_cat03_explains_user_parameterization_and_content_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()

    class Evidence:
        @staticmethod
        def _table(headers, rows, **_kwargs):
            return "|".join(str(value) for row in rows for value in row)

        @staticmethod
        def _state_text(_raw, label):
            return label

    html = _ymyl_alignment_html(Evidence, database, "AUD-YMYL")
    assert "Contexto YMYL × conteúdo observado" in html
    assert "parametrização do usuário foi respeitada" in html
    assert "SC-P11, SC-P12 e SC-P13" in html
    assert "Há lacunas YMYL acionáveis" in html
    assert "Exatidão contratual ou regulatória das alegações" in html
    assert "Não verificada nesta análise" in html
    assert "não equivale a uma alegação corroborada por documento oficial" in html
    assert "não significa que a alegação seja falsa" in html
    ai_execution_state.clear_current_ai_execution()


def test_cat08_ymyl_block_explains_why_content_needs_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    html = _ymyl_analysis_context_html(
        database,
        "AUD-YMYL",
        catalog_report_analysis,
    )
    assert "Parametrização × interpretação" in html
    assert "não de a IA ter sobrescrito ou rejeitado a parametrização do usuário" in html
    assert "SC-P11 - Suporte observável de claims" in html
    assert "SC-P12 - Autoria e responsabilidade" in html
    assert "Mudança recomendada" not in html
    assert "Remediação necessária ainda sem ação individual" in html
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

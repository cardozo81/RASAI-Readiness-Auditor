from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import CATALOG_REPORT_CONTRACT_VERSION
from rasai.catalog_report_site import materialize_catalog_report_site


AUDIT_ID = "AUD-CATALOG-002"


def _workspace(tmp_path: Path):
    root = tmp_path / AUDIT_ID
    root.mkdir()
    database = root / "audit.db"
    configuration = {
        "targets": ["https://example.test/"],
        "audit_catalog": {
            "version": "1",
            "selected": ["CAT-08"],
            "ai_enabled": True,
            "items": [
                {
                    "id": "CAT-08",
                    "catalog_id": "CAT-08",
                    "selected": True,
                    "status": "APTO",
                    "detail": "URL única e IA configurada",
                    "ai_mode": "REQUIRED",
                    "ai_execution_enabled": True,
                    "capability_ids": ["deep-analysis"],
                }
            ],
        },
    }
    digest = configuration_hash(configuration)
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY, project_name TEXT, status TEXT,
                completion_status TEXT, created_at TEXT, started_at TEXT, completed_at TEXT
            );
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY, configuration_json TEXT, configuration_hash TEXT
            );
            CREATE TABLE improvement_intelligence_runs(
                audit_id TEXT, status TEXT, language TEXT, findings_count INTEGER,
                recommendations_count INTEGER, summary TEXT
            );
            CREATE TABLE improvement_intelligence_findings(
                audit_id TEXT, finding_id TEXT, title TEXT, detail TEXT,
                domain TEXT, severity TEXT, source TEXT
            );
            CREATE TABLE improvement_intelligence_recommendations(
                audit_id TEXT, recommendation_id TEXT, title TEXT, recommendation TEXT,
                priority TEXT, source_finding_id TEXT
            );
            CREATE TABLE ai_provider_attempts(
                audit_id TEXT, attempt_id TEXT, provider TEXT, model TEXT, status TEXT,
                attempt_index INTEGER, input_tokens INTEGER, output_tokens INTEGER,
                reasoning_tokens INTEGER, total_tokens INTEGER, estimated_cost REAL,
                semantic_contract_version TEXT, started_at TEXT, finished_at TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, "Projeto", "SUCCESS", "COMPLETE", "a", "b", "c"),
        )
        con.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?,?)",
            (AUDIT_ID, json.dumps(configuration, ensure_ascii=False), digest),
        )
        con.execute(
            "INSERT INTO improvement_intelligence_runs VALUES (?,?,?,?,?,?)",
            (AUDIT_ID, "COMPLETE", "pt-BR", 1, 1, "Uma melhoria prioritária foi identificada."),
        )
        con.execute(
            "INSERT INTO improvement_intelligence_findings VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, "IMP-1", "Problema de performance", "LCP elevado", "PERFORMANCE", "HIGH", "LIGHTHOUSE"),
        )
        con.execute(
            "INSERT INTO improvement_intelligence_recommendations VALUES (?,?,?,?,?,?)",
            (AUDIT_ID, "REC-1", "Reduzir LCP", "Otimizar o recurso principal.", "HIGH", "IMP-1"),
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (AUDIT_ID, "AIA-1", "OPENAI", "model-x", "SUCCESS", 1, 100, 50, 10, 160, 0.01, "IMPROVEMENT-INTELLIGENCE-001", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"),
        )
        con.commit()
    finally:
        con.close()
    return SimpleNamespace(root=root, database=database)


def test_contract_002_keeps_shared_structure_and_adds_capture_context(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    assert CATALOG_REPORT_CONTRACT_VERSION == "CATALOG-REPORT-002"
    assert (report / "capture-context.html").is_file()
    cat = (report / "cat-08.html").read_text(encoding="utf-8")
    for label in (
        "Resumo", "Escopo solicitado", "Configuração efetiva", "Execução", "Resultados",
        "Evidências", "Análise e interpretação", "Remediações", "Detalhes técnicos",
    ):
        assert label in cat


def test_cat08_uses_final_persisted_result_and_contextual_modal(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    cat = (report / "cat-08.html").read_text(encoding="utf-8")

    assert "CONCLUÍDO" in cat
    assert "Problemas correlacionados" in cat
    assert cat.count("data-modal-open='improvement-") == 1
    assert cat.count("<dialog id='improvement-") == 1
    assert "Origem: CAT-04" in cat


def test_ai_integrations_uses_human_labels_not_generic_field_columns(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    html = (report / "ai-integrations.html").read_text(encoding="utf-8")

    assert "Campo 1" not in html
    assert "Requisições de IA" in html
    assert "Tokens de entrada" in html
    assert "Custo estimado" in html
    assert html.count("data-modal-open='ai-attempt-") == 1
    assert html.count("<dialog id='ai-attempt-") == 1


def test_unselected_catalog_remains_not_requested(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    search = (report / "cat-05.html").read_text(encoding="utf-8")
    assert "NÃO SOLICITADO" in search

"""Isolated #109 regressions from independently verified AUD smoke leftovers.

These tests exercise only pure typed display helpers and one small read-only
AI-dependency projection. No audit, browser, network, collector, or provider.
"""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.accepted_audit_refinements import _public_exact_change
from rasai.ai_dependency_reporting import (
    _dependency_label, _dependency_state_label, dependency_html,
)
from rasai.catalog_report_evidence import _discovery_observed_public
from rasai.catalog_report_integrations import _external_details_public_text
from rasai.recommendation_governance_reporting import _conflict_group_label
from rasai.request_remediation_intelligence import (
    _FAMILY_META, _FAMILY_PUBLIC_LABELS, _public_request_family,
)
from rasai.report_presentation import humanize_report_html


def test_cat01_typed_discovery_observations_keep_original_untouched() -> None:
    original = {
        "discovery_sources": ["ROOT_CONVENTION"],
        "http_status": 404,
        "scope_path": "/",
        "state": "ABSENT",
    }
    rendered = _discovery_observed_public(original)
    assert rendered["discovery_sources"] == [
        "Verificação do caminho convencional na raiz"
    ]
    assert original["discovery_sources"] == ["ROOT_CONVENTION"]
    assert rendered["http_status"] == 404
    html = humanize_report_html(
        "<div class='pre'>" + json.dumps(rendered, ensure_ascii=False) + "</div>",
        page_name="cat-01.html",
    )
    assert "Condição técnica não catalogada" not in html
    strategy = {"strategy": "ROOT_PLUS_EXPLICIT_DISCOVERY", "candidate_count": 1}
    assert "indicações explícitas" in _discovery_observed_public(strategy)["strategy"]
    assert strategy["strategy"] == "ROOT_PLUS_EXPLICIT_DISCOVERY"
    unknown = {"discovery_sources": ["FUTURE_UNKNOWN"], "strategy": "FUTURE_UNKNOWN"}
    assert "não classificada" in _discovery_observed_public(unknown)["strategy"]
    assert "não classificada" in _discovery_observed_public(unknown)["discovery_sources"][0]


def test_cat09_conflict_family_and_exact_actions_are_contextual() -> None:
    assert _conflict_group_label("DISCOVERY_RESOURCE_STATE") == (
        "Conflito de estado dos recursos de descoberta"
    )
    assert _conflict_group_label("UNRECOGNIZED_GROUP") == (
        "Grupo de conflito não classificado"
    )
    assert set(_FAMILY_META) == set(_FAMILY_PUBLIC_LABELS)
    assert _public_request_family("REQUEST_OTHER") == "Outra falha de requisição"
    assert _public_request_family("FUTURE_EVENT") == "Família técnica não classificada"
    change = (
        "Ação: CORRECT_RESOURCE · Alvo: robots.txt · Local: /robots.txt · "
        "Ausência válida não deve ser tratada como defeito."
    )
    shown = _public_exact_change(change)
    assert "Ação: Revisar ou corrigir o recurso" in shown
    assert "Ausência válida não deve ser tratada como defeito." in shown
    assert "CORRECT_RESOURCE" not in shown
    assert "CORRECT_RESOURCE" in change
    for code in ("REVIEW_AND_CORRECT", "CORRECT_STRUCTURED_DATA", "ADD_OR_CORRECT"):
        assert code not in _public_exact_change(f"Ação: {code} · Alvo: observado")
    assert "Ação técnica não classificada" in _public_exact_change(
        "Ação: UNKNOWN_FUTURE_ACTION · Alvo: observado"
    )
    assert _public_exact_change(None) == "-"


def test_external_typed_details_keep_valid_json_and_source_values() -> None:
    original = {
        "dataset": {"source": "NPM_WEB_FEATURES", "version": "3.40.0"},
        "boundary": (
            "SUCCESS means deterministic classification of directly observable "
            "feature signals within this bounded detector scope"
        ),
        "detected_features": 88,
    }
    new = json.loads(_external_details_public_text(original))
    assert new["dataset"] == {"source": "Pacote npm web-features", "version": "3.40.0"}
    assert "escopo delimitado" in new["boundary"]
    assert new["detected_features"] == 88
    assert original["dataset"]["source"] == "NPM_WEB_FEATURES"

    original_crux = {
        "source_type": "CHROME_UX_REPORT_HISTORY",
        "capture_method": "DIRECT_OFFICIAL_API",
        "metadata": {"scope_policy": "AUDITED_ORIGIN_ONLY", "form_factor": "PHONE"},
        "dataset_id": "OBS-SAMPLE",
        "rows": 120,
    }
    crux = json.loads(_external_details_public_text(json.dumps(original_crux)))
    assert crux["source_type"] == "Histórico do Chrome UX Report"
    assert crux["capture_method"] == "Consulta direta à API oficial"
    assert crux["metadata"]["scope_policy"] == "Somente a origem auditada"
    assert crux["dataset_id"] == "OBS-SAMPLE"
    assert crux["rows"] == 120
    assert original_crux["capture_method"] == "DIRECT_OFFICIAL_API"


def test_ai_prerequisites_have_distinct_public_names_and_rows(tmp_path) -> None:
    assert _dependency_label("EVIDENCE_SEALED") != _dependency_label(
        "SEMANTIC_EVIDENCE_CONTEXT"
    )
    assert _dependency_state_label("SUCCESS") == "Concluída"
    path = tmp_path / "audit.db"
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE ai_dependency_snapshots (
            dependency_snapshot_id TEXT, audit_id TEXT, purpose TEXT,
            scope_key TEXT, expected_json TEXT, present_json TEXT,
            missing_json TEXT, evidence_ids_json TEXT, context_fingerprint TEXT,
            ready INTEGER, contract_version TEXT, created_at TEXT
        )"""
    )
    con.execute(
        "INSERT INTO ai_dependency_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "AID-SAMPLE", "AUD-SAMPLE", "SEMANTIC_AI", "AUDIT",
            json.dumps(["EVIDENCE_SEALED", "SEMANTIC_EVIDENCE_CONTEXT"]),
            json.dumps({
                "EVIDENCE_SEALED": "SUCCESS",
                "SEMANTIC_EVIDENCE_CONTEXT": "SUCCESS",
            }),
            "[]", "[]", "sample-fingerprint", 1, "AI-DEPENDENCY-002",
            "2026-09-30T16:45:00Z",
        ),
    )
    con.commit()
    con.close()
    html = humanize_report_html(
        dependency_html(path, SimpleNamespace(audit_id="AUD-SAMPLE")),
        page_name="ai-integrations.html",
    )
    assert html.count("Evidências determinísticas seladas") >= 2
    assert html.count("Contexto semântico baseado nas evidências") >= 2
    assert html.count("Concluída") == 2
    assert "Condição técnica não catalogada" not in html
    assert "EVIDENCE_SEALED" not in html
    assert "SEMANTIC_EVIDENCE_CONTEXT" not in html
    assert html.count("<tr") >= 3  # header + two distinct dependency rows

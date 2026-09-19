from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import CATALOG_REPORT_FILENAMES, CATALOG_REPORT_PAGES
from rasai.catalog_report_model import _load_data
from rasai.directed_analysis import (
    _catalogs_for_candidate,
    _validate_ai_output,
    _validate_references,
    build_strategic_context,
    execute_directed_analysis,
)
from rasai.directed_analysis_reporting import directed_analysis_body


AUDIT_ID = "AUD-DIRECTED"


def _workspace(tmp_path: Path, *, ai_enabled: bool = False):
    root=tmp_path/AUDIT_ID
    root.mkdir()
    database=root/"audit.db"
    configuration={
        "targets":["https://example.test/"],
        "audit_catalog":{
            "version":"1",
            "selected":["CAT-03","CAT-09"],
            "ai_enabled":ai_enabled,
            "items":[
                {"id":"CAT-03","selected":True,"status":"APTO","ai_mode":"OPTIONAL","ai_execution_enabled":ai_enabled},
                {"id":"CAT-09","selected":True,"status":"APTO","ai_mode":"OPTIONAL","ai_execution_enabled":ai_enabled},
            ],
        },
    }
    digest=configuration_hash(configuration)
    connection=sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY,
                project_name TEXT,
                status TEXT,
                completion_status TEXT,
                primary_language TEXT,
                market TEXT
            );
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY,
                configuration_json TEXT,
                configuration_hash TEXT
            );
            CREATE TABLE jsonld_remediation_suggestions(
                suggestion_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                page_id TEXT,
                snapshot_id TEXT,
                device TEXT,
                status TEXT,
                existing_types TEXT,
                proposed_json TEXT,
                improvements TEXT,
                evidence_ids TEXT,
                created_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?)",
            (AUDIT_ID,"Projeto dirigido","SUCCESS","COMPLETE","pt-BR","BR"),
        )
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?,?)",
            (AUDIT_ID,json.dumps(configuration,ensure_ascii=False),digest),
        )
        connection.execute(
            "INSERT INTO jsonld_remediation_suggestions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "J1",AUDIT_ID,"P1","S1","MOBILE","SUGGESTED","[]",
                json.dumps({"@context":"https://schema.org","@type":"Organization"}),
                json.dumps(["Criar JSON-LD de organização"],ensure_ascii=False),
                json.dumps(["EV-J1"]), "2026-09-19T10:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root,database=database)


def test_context_builder_uses_persisted_actions_and_deterministic_catalog_links(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path)

    context, actions, fingerprint=build_strategic_context(audit_id=AUDIT_ID,workspace=workspace)

    assert fingerprint
    assert context["audit"]["audit_id"] == AUDIT_ID
    assert len(actions) == 1
    action=actions[0]
    assert action["source_kind"] == "JSONLD"
    assert {item["dimension"] for item in action["affected_dimensions"]} >= {
        "STRUCTURED_DATA","SEMANTICS","SEO","GEO_SEARCH_AI"
    }
    assert action["source_refs"][0]["catalog_id"] == "CAT-03"
    assert action["evidence_refs"]
    assert action["remediation_refs"][0]["href"] == "cat-09.html#rem-jsonld-j1"
    _validate_references(actions)


def test_request_action_can_be_supported_by_cat06_and_cat07() -> None:
    catalogs=_catalogs_for_candidate({
        "source_kind":"REQUEST_REMEDIATION",
        "source_catalog":"CAT-06/CAT-07",
        "row":{},
    })
    assert catalogs == ("CAT-06","CAT-07")


def test_invalid_or_ai_invented_reference_is_rejected() -> None:
    with pytest.raises(ValueError,match="unresolvable catalog reference"):
        _validate_references([{
            "action_id":"ACT-X",
            "source_refs":[{"catalog_id":"CAT-99","section_id":"results","href":"cat-99.html#results"}],
            "evidence_refs":[{"catalog_id":"CAT-03","section_id":"results","href":"cat-03.html#results"}],
            "remediation_refs":[],
        }])

    actions=[{"action_id":"ACT-1"}]
    payload={
        "summary":{
            "strengths":[],"fragilities":[],"risks":[],"opportunities":[],
            "insufficient_evidence":[],"plan_overview":""
        },
        "actions":[{
            "action_id":"ACT-INVENTED",
            "reason":"x","primary_objective":"x",
            "affected_dimensions":[{"dimension":"SEO","expected_gain":"MEDIUM"}],
            "priority":"MEDIUM","effort":"LOW","confidence":"MEDIUM","confidence_reason":"x",
            "dependencies":[],"implementation_guidance":[],"validation_steps":[],
        }],
        "roadmap":[],
    }
    with pytest.raises(ValueError,match="unknown action_id"):
        _validate_ai_output(payload,actions)


def test_ai_disabled_persists_technical_actions_without_inventing_strategy(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path,ai_enabled=False)

    result=execute_directed_analysis(audit_id=AUDIT_ID,workspace=workspace)

    assert result.status == "DISABLED"
    assert result.actions_count == 1
    assert result.ai_actions_count == 0
    connection=sqlite3.connect(workspace.database)
    connection.row_factory=sqlite3.Row
    try:
        run=connection.execute("SELECT * FROM directed_analysis_runs WHERE audit_id=?",(AUDIT_ID,)).fetchone()
        action=connection.execute("SELECT * FROM directed_analysis_actions WHERE audit_id=?",(AUDIT_ID,)).fetchone()
    finally:
        connection.close()
    assert run["status"] == "DISABLED"
    assert run["provider"] is None
    assert action["analysis_state"] == "PERSISTED_SOURCE"
    assert action["priority"] is None
    assert action["confidence"] is None


def test_ai_enabled_enriches_only_existing_action_and_persists_strategy(monkeypatch, tmp_path: Path) -> None:
    import rasai.directed_analysis as feature

    workspace=_workspace(tmp_path,ai_enabled=True)
    fake_config=SimpleNamespace(provider="openai",model="model-test",reasoning="HIGH",language="pt-BR")
    monkeypatch.setattr(feature,"_provider_config",lambda *_args,**_kwargs: fake_config)
    monkeypatch.setattr(feature,"_target_context",lambda *_args,**_kwargs: SimpleNamespace(snapshot_id="S1",url="https://example.test/"))

    def fake_ai_analyze(*, actions, **_kwargs):
        action_id=actions[0]["action_id"]
        return (
            {
                "strengths":["Evidência técnica disponível"],
                "fragilities":["Dados estruturados ausentes"],
                "risks":[],"opportunities":["Criar marcação estruturada"],
                "insufficient_evidence":[],"plan_overview":"Executar e revalidar.",
            },
            {action_id:{
                "reason":"A evidência persistida sustenta a ação.",
                "primary_objective":"Melhorar dados estruturados",
                "affected_dimensions":[
                    {"dimension":"STRUCTURED_DATA","expected_gain":"HIGH"},
                    {"dimension":"SEO","expected_gain":"MEDIUM"},
                    {"dimension":"GEO_SEARCH_AI","expected_gain":"MEDIUM"},
                ],
                "priority":"HIGH","effort":"LOW","confidence":"HIGH",
                "confidence_rationale":"Evidência direta na auditoria.",
                "dependencies":[],"implementation_guidance":["Aplicar a sugestão persistida."],
                "validation_steps":["Reexecutar CAT-03 e confirmar o resultado."],
                "analysis_state":"AI_ANALYZED",
            }},
            [{"phase":"Ganho rápido","objective":"Corrigir a base semântica","action_ids":[action_id]}],
            {"synthetic":"validated"},
            None,
        )

    monkeypatch.setattr(feature,"_ai_analyze",fake_ai_analyze)

    result=execute_directed_analysis(audit_id=AUDIT_ID,workspace=workspace)

    assert result.status == "COMPLETE"
    assert result.ai_actions_count == 1
    connection=sqlite3.connect(workspace.database); connection.row_factory=sqlite3.Row
    try:
        run=connection.execute("SELECT * FROM directed_analysis_runs WHERE audit_id=?",(AUDIT_ID,)).fetchone()
        action=connection.execute("SELECT * FROM directed_analysis_actions WHERE audit_id=?",(AUDIT_ID,)).fetchone()
    finally:
        connection.close()
    assert run["provider"] == "openai"
    assert json.loads(run["roadmap_json"])[0]["phase"] == "Ganho rápido"
    assert action["analysis_state"] == "AI_ANALYZED"
    assert action["priority"] == "HIGH"
    assert action["effort"] == "LOW"
    assert action["confidence"] == "HIGH"


def test_report_renders_strategy_and_menu_contract_contains_page(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path,ai_enabled=False)
    execute_directed_analysis(audit_id=AUDIT_ID,workspace=workspace)
    data=_load_data(AUDIT_ID,workspace.database)

    html=directed_analysis_body(workspace.database,data)

    assert "Análise Direcionada" in html
    assert "Resumo estratégico" in html
    assert "O que corrigir para obter maior ganho transversal" in html
    assert "Rastreabilidade CAT → seção → assunto" in html
    assert "cat-09.html#rem-jsonld-j1" in html
    assert "directed-analysis.html" in CATALOG_REPORT_FILENAMES
    page=next(item for item in CATALOG_REPORT_PAGES if item.filename=="directed-analysis.html")
    assert page.group == "Estratégia"
    assert page.catalog_id is None

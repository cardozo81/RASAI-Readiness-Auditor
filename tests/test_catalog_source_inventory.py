from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_catalog_state import (
    _catalog_source_count,
    _catalog_source_specs,
    _configuration_rows,
)



def test_catalog_source_inventory_covers_material_decision_tables() -> None:
    cat03 = {table for table, _label in _catalog_source_specs("CAT-03")}
    assert {
        "semantic_coherence_assessments",
        "semantic_property_signals",
        "property_semantic_summaries",
        "content_context_interpretations",
    }.issubset(cat03)

    cat05 = {table for table, _label in _catalog_source_specs("CAT-05")}
    assert {
        "serp_competitive_analyses",
        "serp_competitive_results",
        "serp_competitive_pages",
        "serp_competitive_ai_analyses",
    }.issubset(cat05)

    cat09 = {table for table, _label in _catalog_source_specs("CAT-09")}
    assert {
        "recommendation_governance",
        "request_remediation_ai",
        "request_remediation_evidence",
        "root_cause_precision",
    }.issubset(cat09)


def test_related_child_evidence_is_counted_for_catalog_inventory(tmp_path) -> None:
    database=tmp_path/"audit.db"
    con=sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE serp_competitive_analyses(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            CREATE TABLE serp_competitive_results(
                observation_id TEXT NOT NULL,
                position INTEGER NOT NULL
            );
            CREATE TABLE element_observations(
                element_observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            CREATE TABLE finding_element_observations(
                finding_id TEXT NOT NULL,
                element_observation_id TEXT NOT NULL
            );
            """
        )
        con.execute("INSERT INTO serp_competitive_analyses VALUES ('SERP-1','AUD')")
        con.executemany("INSERT INTO serp_competitive_results VALUES (?,?)",[("SERP-1",1),("SERP-1",2)])
        con.execute("INSERT INTO element_observations VALUES ('EO-1','AUD')")
        con.executemany("INSERT INTO finding_element_observations VALUES (?,?)",[("F-1","EO-1"),("F-2","EO-1")])
        con.commit()
        assert _catalog_source_count(con,"serp_competitive_results","AUD")==2
        assert _catalog_source_count(con,"finding_element_observations","AUD")==2
    finally:
        con.close()


def test_cat03_configuration_rows_expose_frozen_editorial_controls() -> None:
    data=SimpleNamespace(
        configuration={
            "settings":{
                "environment":{
                    "RASAI_CONTENT_RISK_PROFILE":"ymyl",
                    "RASAI_YMYL_CATEGORY":"auto",
                    "RASAI_PAGE_PURPOSE":"product-service",
                    "RASAI_INTENDED_AUDIENCE":"general",
                    "RASAI_EXPERIENCE_REQUIREMENT":"not-expected",
                    "RASAI_FRESHNESS_SENSITIVITY":"low",
                    "RASAI_CONTENT_ORIGIN":"first-party",
                }
            }
        },
        config_hash="same",
        computed_hash="same",
        selected={"CAT-03"},
        targets=("https://example.test/",),
        catalog_items={"CAT-03":{"ai_mode":"OPTIONAL","ai_execution_enabled":True}},
    )
    rows=_configuration_rows(data,"CAT-03")
    values={str(row[0]):str(row[1]) for row in rows}
    assert values["Perfil de risco"]=="YMYL (ymyl)"
    assert values["Categoria YMYL"]=="Automático"
    assert values["Propósito da página"]=="Produto ou serviço (product-service)"
    assert values["Público pretendido"]=="Público geral (general)"
    assert values["Requisito de experiência"]=="Não esperada (not-expected)"
    assert values["Sensibilidade à atualização"]=="Baixa (low)"
    assert values["Origem do conteúdo"]=="Conteúdo próprio (first-party)"

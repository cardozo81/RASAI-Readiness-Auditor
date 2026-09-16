from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_adherence import (
    _audit_hero,
    _cat05_capability_states,
    _human_status_value,
    _normalize_configuration_rows,
)
from rasai import execution_adherence_refinement as execution_refinement


def test_cat05_resolves_each_independent_capability_from_own_evidence(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE serp_observations(audit_id TEXT, observation_id TEXT)")
        connection.execute("INSERT INTO serp_observations VALUES (?,?)", ("AUD-1", "SERP-1"))
        connection.commit()
    finally:
        connection.close()

    data = SimpleNamespace(
        audit_id="AUD-1",
        selected={"CAT-05"},
        work_items=[],
        configuration={"search_intelligence": {"enabled": True}},
    )
    states = _cat05_capability_states(database, data)

    assert states["search-intelligence"] == "Concluída"
    assert states["google-search-console"] == "Não requerida nesta AUD"
    assert states["ai-visibility"] == "Não requerida nesta AUD"
    assert states["observability"] == "Não requerida nesta AUD"


def test_cat05_uses_fulfillment_state_when_source_was_requested_but_not_materialized(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    data = SimpleNamespace(
        audit_id="AUD-1",
        selected={"CAT-05"},
        configuration={"search_intelligence": {"enabled": False}},
        work_items=[
            {"component": "GOOGLE_SEARCH_CONSOLE", "status": "NOT_CONFIGURED"},
            {"component": "AI_VISIBILITY", "status": "REQUESTED_NOT_EXECUTED"},
        ],
    )

    states = _cat05_capability_states(database, data)
    assert states["google-search-console"] == "Não configurado"
    assert states["ai-visibility"] == "Solicitado, não executado"


def test_hero_separates_logical_result_from_base_audit_limitations() -> None:
    data = SimpleNamespace(
        audit_id="AUD-1",
        targets=("https://example.test/",),
        selected={"CAT-01", "CAT-05"},
        fulfillment={"processing_status": "COMPLETE"},
        audit={
            "project_name": "Projeto",
            "completion_status": "COMPLETE_WITH_LIMITATIONS",
            "limitations": '["RENDERED_DISCOVERY_GAP:10"]',
        },
    )

    html = _audit_hero(data, "Relatório", "Resumo")
    assert "Resultado lógico da AUD" in html
    assert "Auditoria-base" in html
    assert "Concluído com limitações" in html
    assert "Lacuna na descoberta renderizada: 10" in html


def test_public_status_and_configuration_terms_are_portuguese() -> None:
    assert _human_status_value("REQUESTED_NOT_EXECUTED") == "Solicitado, não executado"
    assert _human_status_value("BROWSER_UNAVAILABLE") == "Navegador indisponível"

    rows = _normalize_configuration_rows(
        [
            ("Search Intelligence", "Habilitado", "Plano congelado"),
            ("Dispositivo", "Mobile", "Plano congelado"),
            ("Categorias Lighthouse", "performance · accessibility · best-practices · seo", "Configuração"),
        ],
        "CAT-05",
    )
    assert rows[0][0] == "Inteligência de busca / SERP"
    assert rows[1][1] == "Dispositivo móvel"
    assert "desempenho" in str(rows[2][1])
    assert "acessibilidade" in str(rows[2][1])
    assert "boas práticas" in str(rows[2][1])


def test_final_execution_boundary_runs_catalog_projection_after_inner_result(monkeypatch) -> None:
    calls: list[str] = []

    def fake_finalize(state) -> None:
        calls.append(str(state.audit_id))

    monkeypatch.setattr(execution_refinement, "finalize_catalog_projection", fake_finalize)
    state = SimpleNamespace(audit_id="AUD-1")
    assert execution_refinement.finalize_after_console_run(state, 0) == 0
    assert calls == ["AUD-1"]


def test_sample_timestamp_registry_is_per_sample() -> None:
    execution_refinement._remember_sample_timestamp("AUD-1", "https://example.test/", "mobile", 1, "T1")
    execution_refinement._remember_sample_timestamp("AUD-1", "https://example.test/", "mobile", 2, "T2")

    assert execution_refinement._take_sample_timestamp("AUD-1", "https://example.test/", "mobile", 1) == "T1"
    assert execution_refinement._take_sample_timestamp("AUD-1", "https://example.test/", "mobile", 2) == "T2"

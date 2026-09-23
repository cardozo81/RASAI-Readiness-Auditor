from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_adherence import (
    _audit_hero,
    _cat05_capability_states,
    _duration_only_apdex,
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


def _limited_data() -> SimpleNamespace:
    return SimpleNamespace(
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


def test_hero_shows_full_base_limitation_only_on_governance_pages() -> None:
    data = _limited_data()
    overview = _audit_hero(data, "Visão geral por catálogos", "Resumo")
    catalog = _audit_hero(data, "CAT-04 · Web Performance", "Resumo")

    assert "Resultado lógico da AUD" in overview
    assert "Auditoria-base" in overview
    assert "Concluído com limitações" in overview
    assert "Lacuna na descoberta renderizada: 10" in overview

    assert "Auditoria-base com 1 limitação(ões)" in catalog
    assert "Ver contexto e limitações da auditoria-base" in catalog
    assert "Lacuna na descoberta renderizada: 10" not in catalog


def test_public_status_and_configuration_terms_are_portuguese() -> None:
    assert _human_status_value("REQUESTED_NOT_EXECUTED") == "Solicitado, não executado"
    assert _human_status_value("BROWSER_UNAVAILABLE") == "Navegador indisponível"
    assert _human_status_value("TECHNICAL_ERROR") == "Erro técnico"
    assert _human_status_value("FAIL") == "Não aprovado"

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


def test_duration_only_apdex_is_separate_from_error_forced_classification() -> None:
    samples = [
        {"classification": "FRUSTRATED", "kpm_value_ms": 1000.0},
        {"classification": "FRUSTRATED", "kpm_value_ms": 2500.0},
        {"classification": "FRUSTRATED", "kpm_value_ms": 5000.0},
    ]
    run = {"satisfied_threshold_seconds": 3.0, "frustrated_threshold_seconds": 12.0}

    score, valid, satisfied, tolerating, frustrated = _duration_only_apdex(samples, run)
    assert score == 5 / 6
    assert (valid, satisfied, tolerating, frustrated) == (3, 2, 1, 0)


def test_final_execution_boundary_runs_catalog_projection_after_inner_result(monkeypatch) -> None:
    calls: list[str] = []

    def fake_finalize(state) -> None:
        calls.append(str(state.audit_id))

    monkeypatch.setattr(execution_refinement, "finalize_catalog_projection", fake_finalize)
    state = SimpleNamespace(audit_id="AUD-1")
    assert execution_refinement.finalize_after_console_run(state, 0) == 0
    assert calls == ["AUD-1"]


def test_m25_persisted_sample_keeps_its_individual_capture_timestamp() -> None:
    from rasai import m25_apdex_experience as m25

    measurement = m25.UxMeasurement(status="SUCCESS", user_action_duration_ms=1000.0)
    item = m25._Classified(1, "MOBILE", measurement, "SATISFIED", 1000.0, False, "2026-09-17T00:00:01+00:00")
    calibration = m25.Calibration(
        source="MANUAL_CALIBRATION",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=3.0,
        frustrated_threshold_seconds=12.0,
        errors_affect_apdex=True,
        metadata={},
    )
    sample = m25._persisted_sample(
        "AUD-1",
        "PAGE-1",
        "https://example.test/",
        m25._profile_for_device("MOBILE"),
        m25.ExperienceApdexConfig(),
        calibration,
        item,
    )

    assert sample.captured_at == item.captured_at


def test_audit_base_lifecycle_status_is_rendered_in_pt_br() -> None:
    data = SimpleNamespace(
        audit_id="AUD-1",
        targets=("https://example.test/",),
        selected={"CAT-01"},
        fulfillment={},
        audit={"project_name": "Projeto", "status": "ANALYZING"},
    )
    html = _audit_hero(data, "Visão geral por catálogos", "Resumo")
    assert "Auditoria-base" in html
    assert "Analisando" in html
    assert "Analyzing" not in html


def test_audit_base_all_lifecycle_states_use_pt_br_labels() -> None:
    from rasai.domain import AuditStatus
    from rasai.catalog_report_presentation import _status_label

    for status in AuditStatus:
        data = SimpleNamespace(
            audit_id="AUD-1",
            targets=("https://example.test/",),
            selected={"CAT-01"},
            fulfillment={},
            audit={"project_name": "Projeto", "status": status.value},
        )
        html = _audit_hero(data, "Visão geral por catálogos", "Resumo")
        label = _status_label(status.value)
        assert label in html
        if status.value != label:
            assert f">{status.value}<" not in html

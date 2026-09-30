"""Directed #132: initial-AUD Search diagnostics must not be CLI footer text."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai import search_audit_runtime as search
from rasai.audit_fulfillment import list_work_items
from tests.test_search_fulfillment_runtime import AUDIT_ID, _workspace


def _setup(tmp_path: Path, monkeypatch, *, persist: bool):
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("RASAI_SERP_MODE", "live")
    monkeypatch.setenv("RASAI_SERP_PROVIDER", "serpapi")
    monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "fixture-only-key")
    monkeypatch.setattr(search, "_parsed_args", lambda: SimpleNamespace(
        search_queries=["seguro de vida"], search_depth=20,
        search_region="Porto Alegre", search_device="mobile",
        search_competitive=True, search_compare_content=True,
        search_max_content_pages=3, search_content_timeout_seconds=10,
        search_content_max_bytes=2_000_000, search_content_max_redirects=5,
        search_ai_competitive=False, search_ymyl_mode="AUTO",
        market="BR", language="pt-BR", ai_provider="none", ai_model="",
    ))
    monkeypatch.setattr(search, "_target_url", lambda *args: "https://example.com/")
    with sqlite3.connect(workspace.database) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS serp_observations("
            "audit_id TEXT,run_id TEXT,error_code TEXT,error_message TEXT)"
        )
        # Older observations, including a provider-cached one, cannot be used
        # as this execution's diagnostic even when timestamps overlap.
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?)",
            (AUDIT_ID, "SERP-OLDER", "WRONG_HISTORICAL_CODE", "historical response"),
        )

    from rasai.search_intelligence import cli as search_cli
    def fake_search_main(command):
        assert command[command.index("--run-id") + 1].startswith("SERP-AUD")
        assert "--compare-content" in command
        if persist:
            run_id = command[command.index("--run-id") + 1]
            with sqlite3.connect(workspace.database) as con:
                con.execute(
                    "INSERT INTO serp_observations VALUES (?,?,?,?)",
                    (AUDIT_ID, run_id, "SERP_REQUESTED_DEPTH_INCOMPLETE",
                     "O provedor encerrou a paginação após 9 resultado(s); não foi possível comprovar os 20 solicitados."),
                )
        print("Erro: SERP_REQUESTED_DEPTH_INCOMPLETE: diagnóstico específico")
        print("Content HTTP requests: 3")
        return 1
    monkeypatch.setattr(search_cli, "main", fake_search_main)
    return workspace


def test_initial_search_error_uses_current_typed_observation_not_footer(tmp_path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch, persist=True)
    result = search._collector(audit_id=AUDIT_ID, workspace=workspace)
    assert result["collection_state"] == "ERROR"
    assert result["reason"] == "SERP_REQUESTED_DEPTH_INCOMPLETE"
    assert result["detail"].startswith("O provedor encerrou a paginação")
    assert "Content HTTP requests" not in str(result)
    work = next(i for i in list_work_items(workspace, AUDIT_ID) if i.component == "SEARCH_INTELLIGENCE")
    assert work.last_error_code == "SERP_REQUESTED_DEPTH_INCOMPLETE"
    assert work.last_error_message == result["detail"]


def test_initial_search_without_current_observation_uses_safe_fallback_not_historical_row(
    tmp_path, monkeypatch,
):
    workspace = _setup(tmp_path, monkeypatch, persist=False)
    result = search._collector(audit_id=AUDIT_ID, workspace=workspace)
    assert result["reason"] == "SEARCH_EXIT_1"
    assert "Content HTTP requests: 3" not in result["detail"]
    assert "WRONG_HISTORICAL_CODE" not in str(result)


def test_execution_consistency_attempt_ledger_retains_typed_code(tmp_path, monkeypatch):
    from rasai.execution_consistency_runtime import _install_search_attempt_ledger
    workspace = _setup(tmp_path, monkeypatch, persist=True)
    original = search._collector
    try:
        _install_search_attempt_ledger()
        result = search._collector(audit_id=AUDIT_ID, workspace=workspace)
        assert result["reason"] == "SERP_REQUESTED_DEPTH_INCOMPLETE"
        with sqlite3.connect(workspace.database) as con:
            row = con.execute(
                """SELECT a.status,a.error_code,a.error_message
                   FROM audit_fulfillment_attempts a
                   JOIN audit_fulfillment_work_items w USING(work_item_id)
                   WHERE a.audit_id=? AND w.component='SEARCH_INTELLIGENCE'
                   ORDER BY a.started_at DESC LIMIT 1""", (AUDIT_ID,),
            ).fetchone()
        assert row is not None
        assert row[0] == "FAILED_RETRYABLE"
        assert row[1] == "SERP_REQUESTED_DEPTH_INCOMPLETE"
        assert row[2].startswith("O provedor encerrou a paginação")
    finally:
        search._collector = original

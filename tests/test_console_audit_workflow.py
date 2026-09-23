"""Windows-authoritative console workflow regressions for AUD reuse/reprocessing."""
from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import time
from types import ModuleType, SimpleNamespace

import rasai.console_audit_workflow as workflow


def _state(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        audits_root=str(tmp_path),
        input_mode="url",
        target="",
        current_url="-",
        project="Projeto",
        language="pt-BR",
        market="BR",
        device="mobile",
        current_device="MOBILE",
        search_queries=(),
        search_depth=20,
        search_region="",
        search_device="mobile",
        search_competitive=True,
        search_last_status="NOT_REQUESTED",
        search_last_detail="",
        search_last_report="",
        search_last_duration_seconds=None,
        runtime_blocks={},
        ai_provider="none",
        web_performance=False,
        field_source="auto",
        status="READY",
        operation="LOCAL:READY",
        error="",
        audit_id="",
    )


def _console() -> ModuleType:
    module = ModuleType("test_console_audit_workflow_fake")
    module.render_header = lambda state: None
    return module


def test_loaded_state_syncs_visible_target_and_device(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.device = "desktop"
    configuration = {"targets": ["https://example.com/a", "https://example.com/b"]}

    warnings = workflow._synchronize_loaded_state(
        state,
        configuration,
        "AUD-SOURCE",
    )

    assert not warnings
    assert state.current_url == "https://example.com/a (+1)"
    assert state.current_device == "DESKTOP"


def test_search_inputs_are_recovered_from_persisted_serp_when_snapshot_has_no_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audit_id = "AUD-SOURCE"
    root = tmp_path / audit_id
    root.mkdir()
    connection = sqlite3.connect(root / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                query TEXT NOT NULL,
                region TEXT,
                device TEXT NOT NULL,
                requested_depth INTEGER NOT NULL,
                provider TEXT NOT NULL,
                data_mode TEXT NOT NULL,
                config_metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE serp_competitive_analyses(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO serp_observations(
                observation_id,audit_id,query,region,device,requested_depth,
                provider,data_mode,config_metadata,collected_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "OBS-1",
                    audit_id,
                    "seguro auto",
                    "BR-RS",
                    "desktop",
                    15,
                    "serpapi",
                    "live",
                    "{}",
                    "2026-09-13T10:00:00+00:00",
                ),
                (
                    "OBS-2",
                    audit_id,
                    "previdência privada",
                    "BR-RS",
                    "desktop",
                    15,
                    "serpapi",
                    "live",
                    "{}",
                    "2026-09-13T10:00:01+00:00",
                ),
            ],
        )
        connection.execute(
            "INSERT INTO serp_competitive_analyses(observation_id,audit_id) VALUES (?,?)",
            ("OBS-1", audit_id),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.delenv("RASAI_SERP_MODE", raising=False)
    monkeypatch.delenv("RASAI_SERP_PROVIDER", raising=False)
    state = _state(tmp_path)

    warnings = workflow._synchronize_loaded_state(
        state,
        {"targets": ["https://example.com/"]},
        audit_id,
    )

    assert state.current_url == "https://example.com/"
    assert state.search_queries == ("seguro auto", "previdência privada")
    assert state.search_depth == 15
    assert state.search_region == "BR-RS"
    assert state.search_device == "desktop"
    assert state.search_competitive is True
    assert state.search_last_status == "PENDING"
    assert any("reconstruídos" in warning for warning in warnings)
    assert workflow.os.environ["RASAI_SERP_PROVIDER"] == "serpapi"
    assert workflow.os.environ["RASAI_SERP_MODE"] == "live"


def test_loaded_summary_exposes_target_and_search_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = _state(tmp_path)
    state.target = "https://example.com/"
    state.current_url = state.target
    state.search_queries = ("seguro auto", "seguro residencial")
    state.search_depth = 20
    state.search_region = "BR"
    state.search_device = "mobile"
    monkeypatch.setenv("RASAI_SERP_MODE", "fixture")
    source = SimpleNamespace(audit_id="AUD-SOURCE")
    console = _console()
    monkeypatch.setattr(workflow, "_dependency_warnings", lambda *args: ())

    with redirect_stdout(StringIO()) as output:
        workflow.render_loaded_configuration_summary(console, state, source)

    rendered = output.getvalue()
    assert "https://example.com/" in rendered
    assert "seguro auto; seguro residencial" in rendered
    assert "Depth" in rendered and "20" in rendered
    assert "Região" in rendered and "BR" in rendered
    assert "Credencial do AUD    : não copiada" in rendered
    assert state.error == ""


def test_reprocess_live_snapshot_reports_running_and_completed_items(tmp_path: Path) -> None:
    audit_id = "AUD-TEST"
    root = tmp_path / audit_id
    root.mkdir()
    connection = sqlite3.connect(root / "audit.db")
    try:
        connection.execute(
            """
            CREATE TABLE audit_fulfillment_work_items(
                audit_id TEXT,
                component TEXT,
                scope_key TEXT,
                status TEXT,
                attempt_count INTEGER,
                required INTEGER
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO audit_fulfillment_work_items(
                audit_id,component,scope_key,status,attempt_count,required
            ) VALUES (?,?,?,?,?,?)
            """,
            [
                (audit_id, "SEMANTIC_AI", "SNAP-1", "RUNNING", 2, 1),
                (audit_id, "WEB_PERFORMANCE", "MOBILE", "SUCCESS", 1, 1),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    snapshot = workflow._reprocess_live_snapshot(
        root,
        audit_id,
        {
            ("SEMANTIC_AI", "SNAP-1"): 1,
            ("WEB_PERFORMANCE", "MOBILE"): 0,
        },
    )

    assert snapshot["total"] == 2
    assert snapshot["attempted"] == 2
    assert snapshot["evaluated"] == 1
    assert snapshot["running"] == ("SEMANTIC_AI", "SNAP-1", "RUNNING")


def test_reprocess_console_shows_live_progress_and_cost_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import rasai.audit_reprocess as reprocess_module
    import rasai.console_cost as cost_module
    import rasai.console_navigation as navigation

    audit_id = "AUD-TEST"
    root = tmp_path / audit_id
    root.mkdir()
    sqlite3.connect(root / "audit.db").close()

    pending = (
        SimpleNamespace(
            component="SEMANTIC_AI",
            scope_key="SNAP-1",
            status="FAILED_RETRYABLE",
            attempt_count=0,
            required=True,
        ),
    )
    successes = (
        SimpleNamespace(component="CORE_AUDIT", scope_key="AUDIT", status="SUCCESS"),
    )
    monkeypatch.setattr(navigation, "_work_item_preview", lambda state, aid: (pending, successes))
    monkeypatch.setattr(
        workflow,
        "_reprocess_live_snapshot",
        lambda *args, **kwargs: {
            "total": 1,
            "evaluated": 0,
            "attempted": 1,
            "running": ("SEMANTIC_AI", "SNAP-1", "RUNNING"),
        },
    )
    monkeypatch.setattr(workflow, "_render_live_reprocess_usage", lambda root: None)

    before = SimpleNamespace(
        ai_attempts=1,
        ai_successes=1,
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=50,
        reasoning_tokens=0,
        total_tokens=150,
        costs=(("USD", 0.01),),
        unpriced_ai_attempts=0,
        web_external_calls=0,
        web_services=(),
    )
    after = SimpleNamespace(
        ai_attempts=2,
        ai_successes=1,
        input_tokens=200,
        cached_input_tokens=0,
        output_tokens=80,
        reasoning_tokens=0,
        total_tokens=280,
        costs=(("USD", 0.02),),
        unpriced_ai_attempts=0,
        web_external_calls=0,
        web_services=(),
    )
    calls = {"usage": 0}

    def fake_usage(workspace):
        calls["usage"] += 1
        return before if calls["usage"] == 1 else after

    monkeypatch.setattr(cost_module, "actual_usage", fake_usage)

    result = SimpleNamespace(
        audit_id=audit_id,
        reprocess_id="RPR-TEST",
        processing_status="PARTIAL_RETRYABLE",
        score_status="PENDING",
        report_status="PRELIMINARY",
        consolidation_eligible=False,
        attempted_items=1,
        successful_items=0,
        skipped_success_items=1,
        remaining_items=1,
        temporal_expired_items=0,
    )

    def fake_reprocess(*args, **kwargs):
        time.sleep(0.02)
        return result

    monkeypatch.setattr(reprocess_module, "reprocess_audit", fake_reprocess)

    console = _console()
    cumulative = {"rendered": False}
    console._render_actual_usage = lambda state: cumulative.__setitem__("rendered", True)
    state = _state(tmp_path)
    answers = iter(["C", ""])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    with redirect_stdout(StringIO()) as output:
        workflow._reprocess_selected(console, state, audit_id)

    rendered = output.getvalue()
    assert "REPROCESSAMENTO EM EXECUÇÃO" in rendered
    assert "análise semântica por IA" in rendered
    assert "CONSUMO DESTA TENTATIVA DE REPROCESSAMENTO" in rendered
    assert "Custo IA estimado" in rendered
    assert "CONSUMO ACUMULADO DO AUD APÓS O REPROCESSAMENTO" in rendered
    assert cumulative["rendered"] is True


def test_entrypoint_installs_audit_workflow_after_navigation() -> None:
    import inspect
    import rasai.console_entrypoint as entrypoint

    source = inspect.getsource(entrypoint.main)
    assert source.index("install_console_navigation") < source.index(
        "install_console_audit_workflow"
    )

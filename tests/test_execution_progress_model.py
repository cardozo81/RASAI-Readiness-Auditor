from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from rasai.audit_progress_runtime import (
    _audit_id,
    _content_ai_ready,
    _flags,
    _rendering_completed,
)
from rasai.console_progress_model import phase_bounds, projected_overall, workload_weights
from rasai.external_observability_progress_runtime import _evidence_ready


def _state(**overrides):
    values = {
        "device": "mobile",
        "ai_provider": "none",
        "content_remediation": False,
        "web_performance": False,
        "web_max_pages": 10,
        "synthetic_apdex": False,
        "apdex_samples": 1,
        "apdex_max_pages": 1,
        "apdex_experience": False,
        "apdex_experience_samples": 1,
        "apdex_experience_max_pages": 1,
        "search_queries": (),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_workload_model_gives_slow_repeated_work_more_weight() -> None:
    state = _state(
        device="desktop",
        web_performance=True,
        synthetic_apdex=True,
        apdex_samples=20,
        apdex_max_pages=1,
    )
    with patch("rasai.console_progress_model._service_ready", return_value=False):
        weights = workload_weights(state)
    assert weights["WEB_PERFORMANCE"] > weights["REPORTING"]
    assert weights["SYNTHETIC_APDEX"] > weights["SCORING"]
    assert weights["ACQUIRING"] > weights["INITIALIZING"]


def test_optional_slow_work_changes_whole_pipeline_projection() -> None:
    base = _state()
    slow = _state(web_performance=True)
    with patch("rasai.console_progress_model._service_ready", return_value=False):
        base_end = phase_bounds(base)["ACQUIRING"][1]
        slow_end = phase_bounds(slow)["ACQUIRING"][1]
    assert slow_end < base_end


def test_measured_stage_maps_continuously_into_dynamic_phase() -> None:
    state = _state()
    with patch("rasai.console_progress_model._service_ready", return_value=False):
        start, end = phase_bounds(state)["ANALYZING"]
        halfway = projected_overall(state, "ANALYZING", 50.0)
    assert halfway is not None
    assert start < halfway < end
    assert halfway == (start + end) / 2.0


class _Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.database = root / "audit.db"


def test_external_api_gate_requires_persisted_core_evidence_not_completed_audit(tmp_path: Path) -> None:
    workspace = _Workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY,status TEXT,completion_status TEXT);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,page_id TEXT);
            INSERT INTO audits VALUES('AUD-PROGRESS','ANALYZING',NULL);
            INSERT INTO pages VALUES('P1','AUD-PROGRESS');
            """
        )
        connection.commit()
    finally:
        connection.close()

    ready, reason = _evidence_ready(workspace=workspace, audit_id="AUD-PROGRESS")
    assert ready is False
    assert reason == "NO_PERSISTED_BROWSER_SNAPSHOT"

    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute("INSERT INTO page_snapshots VALUES('S1','P1')")
        connection.commit()
    finally:
        connection.close()

    ready, reason = _evidence_ready(workspace=workspace, audit_id="AUD-PROGRESS")
    assert ready is True
    assert reason == "READY"


def test_content_remediation_gate_uses_semantic_context_not_future_scoring(tmp_path: Path) -> None:
    workspace = _Workspace(tmp_path)
    flags = _flags(workspace)
    flags.clear()
    flags.update({"SEMANTIC_ANALYSIS", "CONTEXT_COMPARISON"})

    _content_ai_ready((), {"enabled": True}, "AUD-CONTENT", workspace)

    assert "SCORING" not in flags
    assert "RECOMMENDATION_BUILD" not in flags


def test_progress_audit_id_falls_back_to_audit_workspace_name(tmp_path: Path) -> None:
    workspace = SimpleNamespace(
        root=tmp_path / "AUD-TRACE",
        database=tmp_path / "AUD-TRACE" / "audit.db",
    )

    assert _audit_id((), {"workspace": workspace}) == "AUD-TRACE"



def test_rendering_completion_uses_persisted_page_device_universe(tmp_path: Path) -> None:
    workspace = _Workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT);
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,
                page_id TEXT,
                device TEXT,
                browser_metadata TEXT,
                captured_at TEXT
            );
            INSERT INTO pages VALUES('P1','AUD-RENDER');
            INSERT INTO page_snapshots VALUES(
                'S1','P1','MOBILE',
                '{"audit_device_context":["MOBILE"]}',
                '2026-09-29T10:00:00+00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    assert _rendering_completed(workspace, "AUD-RENDER") is True


def test_rendering_completion_log_fallback_is_not_limited_to_last_128k(tmp_path: Path) -> None:
    workspace = _Workspace(tmp_path)
    log = tmp_path / "logs" / "audit.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    event = '{"event":"RENDERING_COMPLETED","audit_id":"AUD-LONG-LOG"}\n'
    filler = '{"event":"SYNTHETIC_SAMPLE","detail":"' + ("x" * 2048) + '"}\n'
    log.write_text(event + filler * 80, encoding="utf-8")

    assert log.stat().st_size > 131072
    assert _rendering_completed(workspace, "AUD-LONG-LOG") is True



def _aud125_comparison_fixture(tmp_path: Path, *, device: str = "MOBILE",
                               comparison_requested: bool = False,
                               create_m8: bool = True) -> _Workspace:
    """Synthetic persisted M8 checkpoint matching the observed MOBILE RPR defect."""
    import json
    workspace = _Workspace(tmp_path)
    with sqlite3.connect(workspace.database) as db:
        db.executescript("""
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT);
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,
                browser_metadata TEXT);
            CREATE TABLE rule_executions(
                rule_execution_id TEXT PRIMARY KEY,audit_id TEXT,rule_id TEXT,
                page_id TEXT,result TEXT,observed_value TEXT,executed_at TEXT);
            INSERT INTO pages VALUES('P1','AUD-M8-RPR');
        """)
        db.execute(
            "INSERT INTO page_snapshots VALUES(?,?,?,?)",
            ("S1", "P1", device, json.dumps({
                "audit_device_context": [device],
                "capture_quality": {"state": "RECOVERED"},
            })),
        )
        if create_m8:
            db.execute(
                "INSERT INTO rule_executions VALUES(?,?,?,?,?,?,?)",
                ("REX-1", "AUD-M8-RPR", "BR-GEO-052", "P1",
                 "PASS" if comparison_requested else "NOT_APPLICABLE",
                 json.dumps({
                     "comparison_requested": comparison_requested,
                     "selected_devices": [device],
                     "reason_code": (
                         "NO_MATERIAL_DEVICE_DIFFERENCE" if comparison_requested
                         else "DEVICE_COMPARISON_DISABLED_BY_CONTEXT"
                     ),
                 }),
                 "2026-10-23T18:01:27Z"),
            )
    return workspace


def test_aud125_rpr_content_ai_gate_accepts_persisted_single_device_m8(tmp_path: Path) -> None:
    from rasai.audit_progress_runtime import (
        _persisted_single_device_comparison_completed,
    )
    workspace = _aud125_comparison_fixture(tmp_path)
    flags = _flags(workspace)
    flags.clear()
    flags.add("SEMANTIC_ANALYSIS")
    assert _persisted_single_device_comparison_completed(workspace, "AUD-M8-RPR")
    _content_ai_ready((), {"enabled": True}, "AUD-M8-RPR", workspace)
    assert "CONTEXT_COMPARISON" in flags
    assert "SCORING" not in flags
    assert "RECOMMENDATION_BUILD" not in flags


def test_aud125_rpr_context_gate_rejects_missing_foreign_or_unproven_m8(tmp_path: Path) -> None:
    from rasai.audit_progress_runtime import (
        _persisted_single_device_comparison_completed,
    )
    workspace = _aud125_comparison_fixture(tmp_path, create_m8=False)
    assert not _persisted_single_device_comparison_completed(workspace, "AUD-M8-RPR")
    with sqlite3.connect(workspace.database) as db:
        db.execute(
            "INSERT INTO rule_executions VALUES(?,?,?,?,?,?,?)",
            ("REX-1", "AUD-OTHER", "BR-GEO-052", "P1", "NOT_APPLICABLE",
             '{"comparison_requested":false,"selected_devices":["MOBILE"],'
             '"reason_code":"DEVICE_COMPARISON_DISABLED_BY_CONTEXT"}',
             "2026-10-23T18:01:27Z"),
        )
    assert not _persisted_single_device_comparison_completed(workspace, "AUD-M8-RPR")


def test_aud125_rpr_context_gate_rejects_mismatched_or_multi_device_scope(tmp_path: Path) -> None:
    from rasai.audit_progress_runtime import _persisted_single_device_comparison_completed
    workspace = _aud125_comparison_fixture(tmp_path)
    with sqlite3.connect(workspace.database) as db:
        db.execute(
            "UPDATE page_snapshots SET browser_metadata=?",
            ('{"audit_device_context":["DESKTOP","MOBILE"]}',),
        )
    assert not _persisted_single_device_comparison_completed(workspace, "AUD-M8-RPR")
    with sqlite3.connect(workspace.database) as db:
        db.execute(
            "UPDATE page_snapshots SET browser_metadata=?",
            ('{"audit_device_context":["MOBILE"]}',),
        )
        db.execute(
            "UPDATE rule_executions SET result='PASS'",
        )
    assert not _persisted_single_device_comparison_completed(workspace, "AUD-M8-RPR")

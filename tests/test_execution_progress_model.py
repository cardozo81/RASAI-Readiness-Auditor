from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from rasai.audit_progress_runtime import _content_ai_ready, _flags
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
        device="both",
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

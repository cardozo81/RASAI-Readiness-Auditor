from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from rasai.console_config import State
from rasai import console_runtime
from rasai import m3_console_progress


def _write_event(root: Path, event: dict[str, object]) -> None:
    path = root / "logs" / "audit.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def test_console_projects_inflight_m3_url_and_exact_context_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(console_runtime, "observe_workspace", lambda _workspace, _state: None)
    monkeypatch.setattr(m3_console_progress, "_INSTALLED", False)
    m3_console_progress.install_m3_render_progress()

    url = "https://example.test/twelve"
    _write_event(
        tmp_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "M3_RENDER_STARTED",
            "url": url,
            "device": "MOBILE",
            "context_index": 12,
            "context_total": 14,
        },
    )
    state = State(status="ACQUIRING", current_url="https://example.test/eleven", current_device="MOBILE")

    console_runtime.observe_workspace(tmp_path, state)

    assert state.current_url == url
    assert state.operation == "BROWSER:CHROMIUM_RENDER"
    progress = console_runtime.runtime_progress_summary(state)
    assert progress is not None
    assert progress.stage_exact is True
    assert round(progress.stage_percent or 0.0, 2) == round((11 / 14) * 100.0, 2)
    assert "snapshot 12/14" in progress.detail
    assert url in progress.detail
    console_runtime.clear_runtime_progress(state)


def test_console_warns_when_started_render_has_no_new_milestone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(console_runtime, "observe_workspace", lambda _workspace, _state: None)
    monkeypatch.setattr(m3_console_progress, "_INSTALLED", False)
    m3_console_progress.install_m3_render_progress()

    _write_event(
        tmp_path,
        {
            "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat(),
            "event": "M3_RENDER_STARTED",
            "url": "https://example.test/stalled",
            "device": "MOBILE",
            "context_index": 12,
            "context_total": 14,
        },
    )
    state = State(status="ACQUIRING")

    console_runtime.observe_workspace(tmp_path, state)

    progress = console_runtime.runtime_progress_summary(state)
    assert progress is not None
    assert "sem novo marco de renderização há" in progress.detail
    console_runtime.clear_runtime_progress(state)

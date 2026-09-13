"""Windows-authoritative console regressions for AUD configuration reuse."""
from __future__ import annotations

import json
from pathlib import Path

from rasai.audit_configuration_reuse_console import _apply_settings, _export_settings
from rasai.console_m23 import State


def test_console_snapshot_never_serializes_api_keys(monkeypatch) -> None:
    state = State()
    state.target = "https://example.com/"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-must-not-be-stored")
    monkeypatch.setenv("RASAI_PAGESPEED_API_KEY", "pagespeed-secret")
    exported = _export_settings(state, ("https://example.com/",))
    serialized = json.dumps(exported, ensure_ascii=False)
    assert "sk-secret-must-not-be-stored" not in serialized
    assert "pagespeed-secret" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "RASAI_PAGESPEED_API_KEY" not in serialized


def test_console_loads_multiple_historical_targets_without_reusing_old_file_path(tmp_path: Path) -> None:
    state = State()
    state.audits_root = str(tmp_path)
    state.max_pages = 3
    configuration = _export_settings(
        state,
        ("https://example.com/a", "https://example.com/b"),
    )
    state.max_pages = 99
    state.target = "https://different.example/"

    warnings = _apply_settings(state, configuration, "AUD-SOURCE")

    assert not warnings
    assert state.max_pages == 3
    assert state.input_mode == "file"
    target_file = Path(state.target)
    assert target_file.parent == tmp_path / ".reused-inputs"
    assert target_file.name == "AUD-SOURCE.txt"
    assert target_file.read_text(encoding="utf-8").splitlines() == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_console_loads_single_target_back_into_url_mode(tmp_path: Path) -> None:
    state = State()
    state.audits_root = str(tmp_path)
    configuration = _export_settings(state, ("https://example.com/one",))
    state.input_mode = "file"
    state.target = "old.txt"

    _apply_settings(state, configuration, "AUD-SOURCE")

    assert state.input_mode == "url"
    assert state.target == "https://example.com/one"

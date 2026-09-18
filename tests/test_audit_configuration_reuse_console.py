"""Windows-authoritative console regressions for AUD configuration reuse."""
from __future__ import annotations

import json
from pathlib import Path

from rasai.audit_configuration_reuse_console import (
    _apply_settings,
    _dependency_warnings,
    _export_settings,
)
from rasai.console_m23 import State
from rasai.console_search_intelligence import SearchConsoleState


def test_console_snapshot_never_serializes_api_keys(monkeypatch) -> None:
    state = SearchConsoleState()
    state.target = "https://example.com/"
    state.search_queries = ("seguro auto", "seguro residencial")
    openai_sentinel = "rasai_test_openai_secret_value"
    pagespeed_sentinel = "rasai_test_pagespeed_secret_value"
    serp_sentinel = "rasai_test_serp_secret_value"
    monkeypatch.setenv("OPENAI_API_KEY", openai_sentinel)
    monkeypatch.setenv("RASAI_PAGESPEED_API_KEY", pagespeed_sentinel)
    monkeypatch.setenv("SERPER_API_KEY", serp_sentinel)
    exported = _export_settings(state, ("https://example.com/",))
    serialized = json.dumps(exported, ensure_ascii=False)
    assert openai_sentinel not in serialized
    assert pagespeed_sentinel not in serialized
    assert serp_sentinel not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "RASAI_PAGESPEED_API_KEY" not in serialized
    assert "SERPER_API_KEY" not in serialized


def test_console_snapshot_preserves_search_execution_inputs() -> None:
    state = SearchConsoleState()
    state.search_queries = ("seguro auto", "seguro residencial")
    state.search_depth = 37
    state.search_region = "Rio Grande do Sul"
    state.search_device = "desktop"
    state.search_competitive = False
    state.search_compare_content = True
    state.search_max_content_pages = 4
    state.search_content_timeout_seconds = 12.5
    state.search_content_max_bytes = 1_500_000
    state.search_content_max_redirects = 2
    state.search_ai_competitive = True
    state.search_ymyl_mode = "ON"

    exported = _export_settings(state, ("https://example.com/",))

    search = exported["search_intelligence"]
    assert search == {
        "enabled": True,
        "queries": ["seguro auto", "seguro residencial"],
        "depth": 37,
        "region": "Rio Grande do Sul",
        "device": "desktop",
        "competitive": False,
        "compare_content": True,
        "max_content_pages": 4,
        "content_timeout_seconds": 12.5,
        "content_max_bytes": 1_500_000,
        "content_max_redirects": 2,
        "ai_competitive": True,
        "ymyl_mode": "ON",
    }


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


def test_console_restores_search_terms_and_parameters(tmp_path: Path) -> None:
    source = SearchConsoleState()
    source.audits_root = str(tmp_path)
    source.search_queries = ("seguro auto", "previdência privada")
    source.search_depth = 15
    source.search_region = "BR-RS"
    source.search_device = "desktop"
    source.search_competitive = False
    source.search_compare_content = True
    source.search_max_content_pages = 4
    source.search_content_timeout_seconds = 12.5
    source.search_content_max_bytes = 1_500_000
    source.search_content_max_redirects = 2
    source.search_ai_competitive = True
    source.search_ymyl_mode = "ON"
    configuration = _export_settings(source, ("https://example.com/",))

    target = SearchConsoleState()
    target.audits_root = str(tmp_path)
    target.search_queries = ()
    target.search_depth = 5
    target.search_region = ""
    target.search_device = "mobile"
    target.search_competitive = True
    target.search_compare_content = False
    target.search_ai_competitive = False

    warnings = _apply_settings(target, configuration, "AUD-SOURCE")

    assert not warnings
    assert target.search_queries == ("seguro auto", "previdência privada")
    assert target.search_depth == 15
    assert target.search_region == "BR-RS"
    assert target.search_device == "desktop"
    assert target.search_competitive is False
    assert target.search_compare_content is True
    assert target.search_max_content_pages == 4
    assert target.search_content_timeout_seconds == 12.5
    assert target.search_content_max_bytes == 1_500_000
    assert target.search_content_max_redirects == 2
    assert target.search_ai_competitive is True
    assert target.search_ymyl_mode == "ON"
    assert target.search_last_status == "PENDING"


def test_loaded_ai_configuration_warns_when_current_credential_is_missing(monkeypatch) -> None:
    state = State()
    state.ai_provider = "openai"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    warnings = _dependency_warnings(state)

    assert any("IA/openai" in warning and "não configurada" in warning for warning in warnings)

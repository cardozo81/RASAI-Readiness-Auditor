"""Windows-authoritative console regressions for AUD configuration reuse."""
from __future__ import annotations

import json

import pytest
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


def test_console_blocks_multiple_historical_targets_without_materializing_file(tmp_path: Path) -> None:
    state = State()
    state.audits_root = str(tmp_path)
    state.max_pages = 3
    configuration = _export_settings(
        state,
        ("https://example.com/a", "https://example.com/b"),
    )
    state.max_pages = 99
    state.target = "https://different.example/"

    with pytest.raises(ValueError, match="novas AUDs exigem exatamente uma URL"):
        _apply_settings(state, configuration, "AUD-SOURCE")

    assert not (tmp_path / ".reused-inputs").exists()
    assert state.max_pages == 99
    assert state.target == "https://different.example/"


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


@pytest.mark.parametrize("field,value", [
    ("depth", float("inf")), ("depth", True),
    ("max_content_pages", float("nan")), ("max_content_pages", True),
    ("content_max_bytes", float("inf")), ("content_max_bytes", True),
    ("content_max_redirects", float("nan")), ("content_max_redirects", False),
])
def test_invalid_historical_search_integer_keeps_current_setting(field, value) -> None:
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    name = {"depth": "search_depth", "max_content_pages": "search_max_content_pages",
            "content_max_bytes": "search_content_max_bytes",
            "content_max_redirects": "search_content_max_redirects"}[field]
    previous = getattr(state, name)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {field: value}}, warnings)
    assert getattr(state, name) == previous
    assert any(field in warning for warning in warnings)


@pytest.mark.parametrize("field,value", [
    ("depth", 1.5), ("depth", "1.5"), ("depth", "-1"),
    ("max_content_pages", 2.9), ("max_content_pages", object()),
    ("content_max_bytes", "1e6"), ("content_max_bytes", 1.2),
    ("content_max_redirects", 0.5), ("content_max_redirects", "2.0"),
])
def test_historical_search_integer_rejects_fractional_or_coerced_value(field, value) -> None:
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    name = {"depth": "search_depth", "max_content_pages": "search_max_content_pages",
            "content_max_bytes": "search_content_max_bytes",
            "content_max_redirects": "search_content_max_redirects"}[field]
    prior = getattr(state, name)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {field: value}}, warnings)
    assert getattr(state, name) == prior
    assert any(field in message for message in warnings)


def test_historical_search_integer_accepts_exact_decimal_strings() -> None:
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "depth": "27", "max_content_pages": 4.0,
        "content_max_bytes": "2000000", "content_max_redirects": "0",
    }}, warnings)
    assert not warnings
    assert (state.search_depth, state.search_max_content_pages,
            state.search_content_max_bytes, state.search_content_max_redirects) == (
                27, 4, 2_000_000, 0,
            )


@pytest.mark.parametrize("queries", [
    ["válida", None], ["válida", {"q": "other"}],
    ["válida", 42], ["x" * 501], ["q"] * 101,
    ["input\\x00hidden"],
])
def test_invalid_historical_query_payload_does_not_erase_session(queries) -> None:
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    state.search_queries = ("consulta existente",)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {"queries": queries}}, warnings)
    assert state.search_queries == ("consulta existente",)
    assert any("search_intelligence.queries" in warning for warning in warnings)


def test_historical_queries_remain_opt_in_and_deduplicated() -> None:
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    state.search_queries = ("consulta anterior",)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "enabled": True, "queries": ["  seguro   auto  ", "seguro auto", " previdência "],
    }}, warnings)
    assert not warnings
    assert state.search_queries == ("seguro auto", "previdência")
    _apply_search_settings(state, {"search_intelligence": {
        "enabled": False, "queries": ["seguro auto"],
    }}, warnings)
    assert state.search_queries == ()


def test_historical_console_rejects_nonstr_targets_without_mutating_session() -> None:
    state = State()
    state.target = "https://example.com/original"
    state.max_pages = 17
    configuration = _export_settings(state, ("https://example.com/target",))
    configuration["targets"] = [42]
    with pytest.raises(ValueError, match="target não textual"):
        _apply_settings(state, configuration, "AUD-SOURCE")
    assert state.target == "https://example.com/original"
    assert state.max_pages == 17


@pytest.mark.parametrize("field,malformed", [
    ("device", ["mobile"]), ("device", 123),
    ("region", {"value": "BR"}), ("region", "x" * 201),
    ("ymyl_mode", ["ON"]), ("ymyl_mode", 1),
])
def test_restored_search_text_fields_do_not_coerce_arbitrary_types(field, malformed):
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    key = {"device": "search_device", "region": "search_region",
           "ymyl_mode": "search_ymyl_mode"}[field]
    before = getattr(state, key)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {field: malformed}}, warnings)
    assert getattr(state, key) == before
    assert any(field in item for item in warnings)


def test_restored_search_text_fields_accept_valid_values():
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "device": " DESKTOP ", "region": " BR-RS ", "ymyl_mode": " on ",
    }}, warnings)
    assert not warnings
    assert state.search_device == "desktop"
    assert state.search_region == "BR-RS"
    assert state.search_ymyl_mode == "ON"


@pytest.mark.parametrize("invalid", [None, 1, 0, [], {}, "maybe", "2"])
def test_invalid_historical_search_enabled_never_changes_operator_queries(invalid):
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    state.search_queries = ("operador",)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "enabled": invalid, "queries": ["consulta externa"],
    }}, warnings)
    assert state.search_queries == ("operador",)
    assert any("search_intelligence.enabled" in warning for warning in warnings)


@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), -2])
def test_invalid_historical_search_timeout_preserves_current_value(invalid):
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    before = state.search_content_timeout_seconds
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "content_timeout_seconds": invalid,
    }}, warnings)
    assert state.search_content_timeout_seconds == before
    assert any("content_timeout_seconds" in warning for warning in warnings)


def test_valid_historical_search_enabled_false_remains_explicit_opt_out():
    from rasai.audit_configuration_reuse_console import _apply_search_settings
    state = SearchConsoleState()
    state.search_queries = ("sessão",)
    warnings = []
    _apply_search_settings(state, {"search_intelligence": {
        "enabled": " false ", "queries": ["outra consulta"],
    }}, warnings)
    assert not state.search_queries
    assert not warnings


def test_configuration_round_trip_ini_then_historical_aud_snapshot(tmp_path, monkeypatch):
    """Save, reopen fresh session, seal nonsecret execution inputs and reuse."""
    from rasai.console_settings import save_console_config, load_console_config
    source = SearchConsoleState()
    source.audits_root = str(tmp_path / "audits")
    source.target = "https://example.org/original"
    source.project = "Roundtrip"
    source.max_pages = 7
    source.search_queries = ("  seguro auto ", "previdência")
    source.search_depth = 18
    source.search_device = "desktop"
    source.search_region = "BR-RS"
    source.search_compare_content = True
    source.search_ai_competitive = False
    ini = tmp_path / "rasai-console.ini"
    save_console_config(source, ini)
    assert ini.is_file()
    fresh = SearchConsoleState()
    loaded = load_console_config(fresh, ini)
    assert not loaded.created
    assert fresh.target == source.target
    assert fresh.project == source.project
    assert fresh.max_pages == source.max_pages
    # Search queries remain execution-only in the console INI.
    assert not fresh.search_queries
    frozen = _export_settings(source, ("https://example.org/original",))
    replacement = SearchConsoleState()
    _apply_settings(replacement, frozen, "AUD-SOURCE")
    assert replacement.target == source.target
    assert replacement.search_queries == ("seguro auto", "previdência")
    assert replacement.search_depth == source.search_depth
    assert replacement.search_region == source.search_region
    assert replacement.search_device == source.search_device
    assert replacement.search_compare_content is True


def test_corrupt_historical_console_section_is_rejected_without_mutation():
    state = SearchConsoleState()
    state.target = "https://current.example/"
    snapshot = _export_settings(state, ("https://source.example/",))
    snapshot["settings"]["console"] = []
    with pytest.raises(ValueError, match="seção console válida"):
        _apply_settings(state, snapshot, "AUD-SOURCE")
    assert state.target == "https://current.example/"

"""#523 detached core INI consumer parity, no audit or provider traffic."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from rasai.console_core_consumer_preflight import inspect_core_consumers


def _save(tmp_path, *, web=True, field="pagespeed", target=True):
    from rasai import console_settings
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_search_intelligence import SearchConsoleState
    _install_search_persistence()
    install()
    state = SearchConsoleState()
    if target:
        state.target = "https://example.test/demo"
    state.project = "PROJ-523"
    state.device = "desktop"
    state.max_pages = 13
    state.market = "BR"
    state.language = "pt-BR"
    state.ai_provider = "openai"
    state.ai_timeout = 181.0
    state.content_remediation = True
    state.technical_remediation = True
    state.web_performance = web
    state.web_max_pages = 0
    state.web_timeout = 132.0
    state.field_source = field
    state.lighthouse_categories = "seo,performance"
    path = tmp_path / "original.ini"
    console_settings.save_console_config(state, path)
    return path


def test_523_core_web_ai_command_reaches_real_parsers_and_consumers(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        original = _save(tmp_path)
        physical = original.read_bytes()
        previous = dict(os.environ)
        outcome = inspect_core_consumers(original, environ={})
        assert outcome["status"] == "CORE_CLI_PARITY_VERIFIED"
        assert outcome["typed_fields_to_cli_verified"] is True
        assert outcome["effective_ai_timeout_verified"] is True
        assert outcome["effective_web_config_verified"] is True
        assert outcome["web_external_prerequisite"] == "NOT_REQUIRED"
        assert outcome["configured_target_in_ini"] is True
        assert outcome["physical_runtime_execution_verified"] is False
        assert outcome["paid_provider_authorized"] is False
        assert outcome["audit_writes"] == outcome["provider_requests"] == 0
        assert "PROJ-523" not in json.dumps(outcome)
        assert os.environ == previous
        assert original.read_bytes() == physical


def test_523_missing_web_crux_credential_never_becomes_runtime_verified(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        original = _save(tmp_path, field="crux")
        physical = original.read_bytes()
        result = inspect_core_consumers(original, environ={})
        assert result["status"] == "EXTERNAL_WEB_PREREQUISITE_UNVERIFIED"
        assert result["typed_fields_to_cli_verified"] is True
        assert result["effective_web_config_verified"] is False
        assert result["web_external_prerequisite"] == "UNVERIFIED"
        assert result["paid_provider_authorized"] is False
        assert original.read_bytes() == physical


def test_523_preparing_without_target_is_not_audit_execution_consent(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        source = _save(tmp_path, web=False, target=False)
        answer = inspect_core_consumers(source, environ={})
        assert answer["status"] == "CLI_PARITY_TARGET_NOT_SET"
        assert answer["typed_fields_to_cli_verified"] is True
        assert answer["effective_web_config_verified"] is True
        assert answer["configured_target_in_ini"] is False
        assert answer["paid_provider_authorized"] is False


def test_523_mutated_real_command_serializer_abstains(tmp_path, monkeypatch):
    from rasai import console_config
    with patch.dict(os.environ, {}, clear=True):
        path = _save(tmp_path)
        original = console_config.build_command
        def malformed(state):
            command = original(state)
            i = command.index("--web-performance-timeout-seconds")
            command[i + 1] = "30"
            return command
        monkeypatch.setattr(console_config, "build_command", malformed)
        outcome = inspect_core_consumers(path, environ={})
        assert outcome["status"] == "CORE_CLI_CONSUMER_MISMATCH"
        assert outcome["typed_fields_to_cli_verified"] is True
        assert outcome["effective_web_config_verified"] is False


def test_523_no_creation_symlink_and_invalid_ini_are_bounded(tmp_path):
    missing = tmp_path / "not-existent.ini"
    assert inspect_core_consumers(missing)["status"] == "SOURCE_UNAVAILABLE"
    assert not missing.exists()
    bad = tmp_path / "bad.ini"
    bad.write_bytes(b"\xff\xfe")
    assert inspect_core_consumers(bad, environ={})["status"] == "INI_LOAD_WARNINGS"
    assert bad.read_bytes() == b"\xff\xfe"
    shortcut = tmp_path / "shortcut.ini"
    try:
        shortcut.symlink_to(bad)
    except (OSError, NotImplementedError):
        return
    assert inspect_core_consumers(shortcut)["status"] == "SOURCE_UNAVAILABLE"

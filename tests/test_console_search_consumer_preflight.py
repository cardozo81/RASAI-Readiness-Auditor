"""#523: search typed INI, governed argv and actual Search audit parser."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from rasai.console_search_consumer_preflight import inspect_search_consumers
from rasai.console_configuration_inventory import main as inventory_main


def _source(tmp_path, *, content_pages=0, redirects=0, ai=False, compare=True):
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    _install_search_persistence()
    install()
    state = SearchConsoleState()
    state.search_queries = ("consulta segura", "consulta comparativa")
    state.search_depth = 20
    state.search_region = "RS"
    state.search_device = "desktop"
    state.search_competitive = True
    state.search_compare_content = compare
    state.search_max_content_pages = content_pages
    state.search_content_timeout_seconds = 12.5
    state.search_content_max_bytes = 1536000
    state.search_content_max_redirects = redirects
    state.search_ai_competitive = ai
    state.search_ymyl_mode = "ON"
    source = tmp_path / "search.ini"
    console_settings.save_console_config(state, source)
    return source


def test_search_preflight_proves_actual_parser_and_preserves_zero_budgets(tmp_path, capsys):
    with patch.dict(os.environ, {}, clear=True):
        path = _source(tmp_path)
        physical = path.read_bytes()
        before = dict(os.environ)
        response = inspect_search_consumers(path, environ={})
        assert response["status"] == "CLI_ADAPTERS_VALIDATED_OFFLINE"
        assert response["configured_query_count"] == 2
        assert response["state_to_cli_parity_verified"] is True
        assert response["physical_aud_execution_verified"] is False
        assert response["per_aud_provider_consent_verified"] is False
        assert response["audit_writes"] == response["provider_requests"] == 0
        assert "consulta segura" not in json.dumps(response, ensure_ascii=False)
        assert "consulta comparativa" not in json.dumps(response, ensure_ascii=False)
        assert os.environ == before
        assert path.read_bytes() == physical
        assert inventory_main(["--ini", str(path), "--verify-search"]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["search_offline_consumer_preflight"]["status"] == (
            "CLI_ADAPTERS_VALIDATED_OFFLINE"
        )
        assert path.read_bytes() == physical


def test_search_preflight_catches_broken_console_serialization(tmp_path, monkeypatch):
    with patch.dict(os.environ, {}, clear=True):
        path = _source(tmp_path)
        from rasai import console_governed_search_runtime as governed
        original = governed._append_search_args
        def corrupt(command, state):
            args = original(command, state)
            index = args.index("--search-content-max-redirects")
            args[index + 1] = "5"
            return args
        monkeypatch.setattr(governed, "_append_search_args", corrupt)
        before = path.read_bytes()
        result = inspect_search_consumers(path, environ={})
        assert result["status"] == "CLI_ARGUMENTS_MISMATCH"
        assert result["state_to_cli_parity_verified"] is False
        assert path.read_bytes() == before


def test_search_preflight_rejects_cross_field_ai_policy_and_secrets(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        source = _source(tmp_path, ai=True, compare=False)
        environment_after_setup = dict(os.environ)
        before = source.read_bytes()
        result = inspect_search_consumers(source, environ={})
        assert result["status"] == "SEMANTIC_CONFIGURATION_CONFLICT"
        assert source.read_bytes() == before
        source.write_text(source.read_text(encoding="utf-8") +
                          "\n[private]\npassword=SENSITIVE_SHOULD_NOT_LEAK\n",
                          encoding="utf-8")
        failed = inspect_search_consumers(source, environ={})
        assert failed["status"] == "CONFIG_ADAPTER_WARNINGS"
        assert "SENSITIVE_SHOULD_NOT_LEAK" not in json.dumps(failed)
        # Fixture preparation initializes runtime defaults in this process.
        # The preflight must preserve that exact environment, not assert that
        # the synthetic fixture itself had no side effects.
        assert os.environ == environment_after_setup


def test_search_preflight_missing_symlink_corrupt_never_writes(tmp_path):
    missing = tmp_path / "missing.ini"
    assert inspect_search_consumers(missing)["status"] == "SOURCE_UNAVAILABLE"
    assert not missing.exists()
    invalid = tmp_path / "invalid.ini"
    invalid.write_bytes(b"\xff\xfe")
    assert inspect_search_consumers(invalid)["status"] == "CONFIG_ADAPTER_WARNINGS"
    assert invalid.read_bytes() == b"\xff\xfe"
    link = tmp_path / "link.ini"
    try:
        link.symlink_to(invalid)
    except (OSError, NotImplementedError):
        return
    assert inspect_search_consumers(link)["status"] == "SOURCE_UNAVAILABLE"


def test_search_resume_snapshot_keeps_explicit_zero_and_sane_nonzeros():
    from rasai.cli_extensions import _search_resume_configuration
    runtime = SimpleNamespace(
        mode="fixture", provider="serpapi", fixture_path=None,
        max_queries=5, max_requests=10, max_depth=100,
        max_competitors=4, timeout_seconds=30.0, retries=0,
        min_interval_seconds=0.0,
    )
    args = SimpleNamespace(
        search_queries=("seguro de vida",),
        search_depth=20, search_region="RS", search_device="desktop",
        search_competitive=True, search_compare_content=True,
        search_max_content_pages=0, search_content_timeout_seconds=12.5,
        search_content_max_bytes=1500000, search_content_max_redirects=0,
        search_ai_competitive=False, search_ymyl_mode="ON",
    )
    zero = _search_resume_configuration(args, runtime)
    assert zero["enabled"] is True
    assert zero["max_content_pages"] == 0
    assert zero["content_max_redirects"] == 0
    assert zero["content_timeout_seconds"] == 12.5
    assert zero["content_max_bytes"] == 1500000
    args.search_max_content_pages = 3
    args.search_content_max_redirects = 2
    positive = _search_resume_configuration(args, runtime)
    assert positive["max_content_pages"] == 3
    assert positive["content_max_redirects"] == 2
    assert zero["provider"] == positive["provider"] == "serpapi"
    args.search_depth = 0
    args.search_content_timeout_seconds = 0
    invalid = _search_resume_configuration(args, runtime)
    assert invalid["depth"] == 0
    assert invalid["content_timeout_seconds"] == 0

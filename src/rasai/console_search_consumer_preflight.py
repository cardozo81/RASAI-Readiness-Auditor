"""#523: safely prove persisted Search inputs reach the governed AUD CLI parser.

No Search API, browser, AUD or remote AI calls. Only a verified bounded INI
copy is loaded into detached console state with environment isolation.
Per-query values, domains, paths, URLs and provider secrets are never output.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from typing import Any, Mapping
from unittest.mock import patch

from rasai.console_apdex_effective_validation import _verified_source

_CONTRACT = "RASAI-SEARCH-CLI-PREFLIGHT-523-001"


def _semantic_configuration(state: Any) -> bool:
    """Prevent accepting structurally parseable but non-executable combinations."""
    queries = tuple(getattr(state, "search_queries", ()) or ())
    content = bool(getattr(state, "search_compare_content", False))
    ai = bool(getattr(state, "search_ai_competitive", False))
    if ai and not content:
        return False
    if any(not isinstance(q, str) or not q.strip() for q in queries):
        return False
    if not 0 < int(state.search_depth) <= 1000:
        return False
    if int(state.search_max_content_pages) < 0:
        return False
    if int(state.search_content_max_bytes) <= 0:
        return False
    if int(state.search_content_max_redirects) < 0:
        return False
    return True


def inspect_search_consumers(
    ini_path: Path, *, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect CLI parity only, never infer authorization or provider readiness."""
    base: dict[str, Any] = {
        "contract": _CONTRACT,
        "status": "NOT_VERIFIABLE", "ini_source_status": "SOURCE_UNAVAILABLE",
        "configured_query_count": None,
        "state_to_cli_parity_verified": False,
        "physical_aud_execution_verified": False,
        "per_aud_provider_consent_verified": False,
        "provider_requests": 0, "audit_writes": 0,
        "source_ini_writes": 0, "values_exposed": False,
    }
    source = Path(ini_path)
    data, identity, status = _verified_source(source)
    if status != "READY":
        return {**base, "status": status, "ini_source_status": status}
    assert data is not None and identity is not None
    digest = sha256(data).digest()
    environment_before = dict(os.environ)
    temp_base = gettempdir()
    try:
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        from rasai.console_search_intelligence import SearchConsoleState
        from rasai.console_ui_refactor import _install_search_persistence
        from rasai.console_complete_persistence import install
        from rasai import console_settings, cli_extensions, search_audit_runtime
        from rasai.console_governed_search_runtime import _append_search_args

        _install_search_persistence()
        install()
        with TemporaryDirectory(prefix="rasai-search-config-523-", dir=temp_base) as tmp:
            copy = Path(tmp) / "operator.ini"
            copy.write_bytes(data)
            state = SearchConsoleState()
            loaded = console_settings.load_console_config(state, copy)
            if loaded.created or loaded.warnings:
                return {**base, "status": "CONFIG_ADAPTER_WARNINGS",
                        "ini_source_status": "READY"}
            if not _semantic_configuration(state):
                return {**base, "status": "SEMANTIC_CONFIGURATION_CONFLICT",
                        "ini_source_status": "READY"}
            queries = tuple(state.search_queries or ())
            if not queries:
                return {**base, "status": "NO_SEARCH_QUERY_INPUT",
                        "ini_source_status": "READY", "configured_query_count": 0}
            args = _append_search_args([], state)
            # The actual child parser is dynamically decorated by the Search
            # runtime. Keep this decoration scoped to this inspector call.
            with patch.object(cli_extensions, "build_parser", cli_extensions.build_parser):
                search_audit_runtime._install_arguments()
                parser = cli_extensions.build_parser()
                parsed = parser.parse_args(["audit", "https://example.invalid", *args])
            expected = {
                "search_queries": [" ".join(q.split()) for q in queries],
                "search_depth": state.search_depth,
                "search_region": state.search_region,
                "search_device": state.search_device,
                "search_competitive": state.search_competitive,
                "search_compare_content": state.search_compare_content,
                "search_max_content_pages": state.search_max_content_pages,
                "search_content_timeout_seconds": state.search_content_timeout_seconds,
                "search_content_max_bytes": state.search_content_max_bytes,
                "search_content_max_redirects": state.search_content_max_redirects,
                "search_ai_competitive": state.search_ai_competitive,
                "search_ymyl_mode": state.search_ymyl_mode,
            }
            matches = all(getattr(parsed, key, object()) == value
                          for key, value in expected.items())
            count = len(queries)
        after, final_identity, final_status = _verified_source(source)
        if (final_status != "READY" or final_identity != identity
                or after is None or sha256(after).digest() != digest):
            return {**base, "status": "SOURCE_CHANGED",
                    "ini_source_status": "SOURCE_CHANGED"}
        return {
            **base,
            "status": "CLI_ADAPTERS_VALIDATED_OFFLINE" if matches
                      else "CLI_ARGUMENTS_MISMATCH",
            "ini_source_status": "READY",
            "configured_query_count": count,
            "state_to_cli_parity_verified": matches,
        }
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError, SystemExit):
        return {**base, "status": "CONFIG_OR_CLI_INVALID",
                "ini_source_status": "READY"}
    finally:
        os.environ.clear()
        os.environ.update(environment_before)


__all__ = ["inspect_search_consumers"]

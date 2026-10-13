"""Issue #523: optional offline M23/M25 consumer preflight from an existing INI.

No audit, browser, external service or native ledger is executed. The active
process environment and one-shot M25 pending configuration are restored.
The result never contains concrete paths, settings, URLs, queries or secrets.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
from typing import Mapping, Any


def inspect_apdex_consumers(
    path: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate that the real Apdex CLI adapters accept a restored INI."""
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install as install_persistence
    from rasai import console_settings
    from rasai.m23_cli import configured_apdex, register_apdex_arguments
    from rasai.m25_apdex_experience import ExperienceApdexConfig
    from rasai.m25_runtime import peek_pending_config, set_pending_config

    base: dict[str, Any] = {
        "contract": "RASAI-APDEX-CONSUMER-PREFLIGHT-523-1",
        "status": "NOT_VERIFIED",
        "active_m23": None,
        "active_m25": None,
        "single_device_enforced": None,
        "load_warning_count": None,
        "external_requests": 0,
        "audit_writes": 0,
        "values_exposed": False,
        "collector_execution_verified": False,
        "dynatrace_live_verified": False,
    }
    candidate = Path(path)
    try:
        if (candidate.is_symlink() or not candidate.is_file()
                or candidate.stat().st_size > 2_000_000):
            return {**base, "status": "SOURCE_UNAVAILABLE"}
        original_bytes = candidate.read_bytes()
    except OSError:
        return {**base, "status": "SOURCE_UNAVAILABLE"}
    if len(original_bytes) > 2_000_000:
        return {**base, "status": "SOURCE_UNAVAILABLE"}
    digest = sha256(original_bytes).digest()

    environment_before = dict(os.environ)
    try:
        # Restore the caller's exact environment whether or not the adapter
        # validation succeeds. Explicit caller env is a test-only substitute.
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        _install_search_persistence()
        install_persistence()
        state = SearchConsoleState()
        result = console_settings.load_console_config(state, candidate)
        if result.created:
            return {**base, "status": "SOURCE_UNAVAILABLE"}
        parser = argparse.ArgumentParser(add_help=False)
        register_apdex_arguments(parser)
        console_settings.sync_nonsecret_runtime_environment(state)
        executor_env = dict(os.environ)
        navigation = configured_apdex(parser.parse_args([]), env=executor_env)
        experience = peek_pending_config()
        try:
            if sha256(candidate.read_bytes()).digest() != digest:
                return {**base, "status": "SOURCE_CHANGED"}
        except OSError:
            return {**base, "status": "SOURCE_CHANGED"}
        return {
            **base,
            "status": "ADAPTERS_VALIDATED_WITH_LOAD_WARNINGS" if result.warnings else "ADAPTERS_VALIDATED_OFFLINE",
            "active_m23": bool(navigation.enabled),
            "active_m25": bool(experience.enabled),
            "single_device_enforced": (
                set(experience.device_mix_dict()) == {state.device.upper()}
                if experience.enabled else None
            ),
            "load_warning_count": len(result.warnings),
        }
    except (OSError, ValueError, TypeError, OverflowError):
        return {**base, "status": "CONFIG_OR_ADAPTER_INVALID"}
    finally:
        os.environ.clear()
        os.environ.update(environment_before)
        set_pending_config(ExperienceApdexConfig(enabled=False))

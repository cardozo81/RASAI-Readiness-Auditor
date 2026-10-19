"""Issue #523: optional offline M23/M25 consumer preflight from an existing INI.

No audit, browser, external service or native ledger is executed. The active
process environment and one-shot M25 pending configuration are restored.
The result never contains concrete paths, settings, URLs, queries or secrets.
"""
from __future__ import annotations

import argparse
from configparser import Error as ConfigError
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from typing import Mapping, Any
from unittest.mock import patch


_SOURCE_LIMIT = 2_000_000


def _verified_source(path: Path) -> tuple[bytes | None, tuple[int, ...] | None, str]:
    """Bound an INI read and tie its bytes to one physical file identity.

    Path and opened descriptor must agree before and after the read. Windows
    creation time is deliberately excluded: it may differ for stat/fstat.
    """
    try:
        if path.is_symlink() or not path.is_file():
            return None, None, "SOURCE_UNAVAILABLE"
        before = path.stat()
        if before.st_size > _SOURCE_LIMIT:
            return None, None, "SOURCE_UNAVAILABLE"
        with path.open("rb") as stream:
            descriptor = os.fstat(stream.fileno())
            data = stream.read(_SOURCE_LIMIT + 1)
        after = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if os.name != "nt":
            fields += ("st_ctime_ns",)
        if (
            path.is_symlink()
            or any(
                getattr(before, field) != getattr(other, field)
                for other in (descriptor, after) for field in fields
            )
            or len(data) != before.st_size
        ):
            return None, None, "SOURCE_CHANGED"
        if len(data) > _SOURCE_LIMIT:
            return None, None, "SOURCE_UNAVAILABLE"
        return data, tuple(getattr(after, field) for field in fields), "READY"
    except OSError:
        return None, None, "SOURCE_UNAVAILABLE"


def _classify_load_warnings(warnings: tuple[str, ...] | list[str]) -> dict[str, int]:
    """Aggregate loader warnings without returning raw keys, paths or values.

    Categories follow console_settings.load_console_config's public warning
    sources. Unknown formats remain unclassified; counts are not assertions
    that a setting was lost or that an Apdex engine executed.
    """
    counts = {
        "unknown_or_nonpersistible_environment": 0,
        "invalid_typed_state": 0,
        "invalid_presentation_timezone": 0,
        "unreadable_ini": 0,
        "other_unclassified": 0,
    }
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    known_sections = set(console_settings._state_values(SearchConsoleState()))
    for warning in warnings:
        if warning.startswith("não foi possível ler "):
            category = "unreadable_ini"
        elif warning.startswith("environment.") and warning.endswith(
            ": variável não reconhecida ou não persistível"
        ):
            category = "unknown_or_nonpersistible_environment"
        elif warning.startswith("RASAI_PRESENTATION_TIMEZONE:"):
            category = "invalid_presentation_timezone"
        elif any(warning.startswith(section + ".") for section in known_sections):
            category = "invalid_typed_state"
        else:
            category = "other_unclassified"
        counts[category] += 1
    return counts


def _classify_environment_warning_reasons(
    warnings: tuple[str, ...] | list[str],
) -> dict[str, int]:
    """Explain rejected environment keys without emitting their names or values.

    The loader rejects keys outside its current non-secret catalog allowlist.
    A removed/unknown key is not necessarily a lost effective setting.
    These counts are diagnostic only, not evidence of runtime consumption.
    """
    from rasai.console_config import is_secret
    from rasai.console_provider_environment import refresh_specs

    catalog = {spec.name for spec in refresh_specs()}
    reasons = {
        "registered_but_excluded": 0,
        "unregistered_secret_pattern": 0,
        "unregistered_name": 0,
        "empty_name": 0,
    }
    prefix = "environment."
    suffix = ": variável não reconhecida ou não persistível"
    for warning in warnings:
        if not (warning.startswith(prefix) and warning.endswith(suffix)):
            continue
        name = warning[len(prefix):-len(suffix)]
        if not name:
            reason = "empty_name"
        elif name in catalog:
            reason = "registered_but_excluded"
        elif is_secret(name):
            reason = "unregistered_secret_pattern"
        else:
            reason = "unregistered_name"
        reasons[reason] += 1
    return reasons


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
    from rasai import m23_cli
    from rasai.m23_cli import register_apdex_arguments
    from rasai.m25_apdex_experience import ExperienceApdexConfig

    base: dict[str, Any] = {
        "contract": "RASAI-APDEX-CONSUMER-PREFLIGHT-523-1",
        "status": "NOT_VERIFIED",
        "active_m23": None,
        "active_m25": None,
        "single_device_enforced": None,
        "load_warning_count": None,
        "load_warning_categories": None,
        "load_warning_environment_reasons": None,
        "external_requests": 0,
        "audit_writes": 0,
        "values_exposed": False,
        "collector_execution_verified": False,
        "dynatrace_live_verified": False,
        # Serialized argv -> real M23/M25 parser in a detached process
        # projection. Never mistake this for a browser/collector execution.
        "cli_argv_parity_verified": False,
        "cli_argv_is_real_execution": False,
    }
    candidate = Path(path)
    original_bytes, original_identity, source_status = _verified_source(candidate)
    if source_status != "READY":
        return {**base, "status": source_status}
    assert original_bytes is not None and original_identity is not None
    digest = sha256(original_bytes).digest()

    environment_before = dict(os.environ)
    # Resolve a writable scratch directory before injecting an isolated
    # environment that may intentionally omit Windows TEMP/TMP variables.
    scratch_directory = gettempdir()
    try:
        # Restore the caller's exact environment whether or not the adapter
        # validation succeeds. Explicit caller env is a test-only substitute.
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        _install_search_persistence()
        install_persistence()
        # Operate on an owned temporary byte-for-byte copy. A deletion or
        # race on the original file can never trigger the loader's
        # missing-file auto-create behavior on the operator's real path.
        with TemporaryDirectory(prefix="rasai-apdex-config-523-", dir=scratch_directory) as tmp:
            copy = Path(tmp) / "operator.ini"
            copy.write_bytes(original_bytes)
            state = SearchConsoleState()
            result = console_settings.load_console_config(state, copy)
            if result.created:
                return {**base, "status": "SOURCE_UNAVAILABLE"}
            # Loader now reports malformed INI as a safe warning instead of
            # raising. Such a source is not a partially usable adapter config.
            if any("não foi possível ler " in warning for warning in result.warnings):
                return {**base, "status": "CONFIG_OR_ADAPTER_INVALID"}
            parser = argparse.ArgumentParser(add_help=False)
            register_apdex_arguments(parser)
            console_settings.sync_nonsecret_runtime_environment(state)
            executor_env = dict(os.environ)
            # configured_apdex normally resets and replaces the one-shot
            # process-global M25 pending config. A read-only inspector must
            # NEVER consume or even temporarily overwrite a real audit's
            # handoff. Capture the same adapter's resolved configuration
            # locally rather than routing its write to the shared runtime.
            captured: list[ExperienceApdexConfig] = []
            def capture_only(config: ExperienceApdexConfig) -> None:
                captured.append(
                    config.validate() if config.enabled
                    else ExperienceApdexConfig(enabled=False)
                )
            with patch.object(m23_cli, "set_pending_config", capture_only):
                navigation = m23_cli.configured_apdex(
                    parser.parse_args([]), env=executor_env
                )
            if len(captured) != 2:
                return {**base, "status": "CONFIG_OR_ADAPTER_INVALID"}
            experience = captured[-1]
            # Verify the actual console command serializer against the CLI
            # parser/consumers, not just state -> projected environment.
            # The serialized argv is held only in memory, never logged or
            # included in the returned diagnostic (Dynatrace paths/JSON can
            # be present as arguments).
            from rasai.console_m23 import append_m23_command
            serialized = append_m23_command([], state)
            captured.clear()
            replayed_navigation = m23_cli.configured_apdex(
                parser.parse_args(serialized), env=executor_env,
            )
            if len(captured) != 2:
                return {**base, "status": "CLI_ARGV_CONTRACT_INVALID"}
            replayed_experience = captured[-1]
            argv_matches = (
                navigation == replayed_navigation
                and experience == replayed_experience
            )
        # A digest alone cannot detect replacement with identical bytes.
        # Recheck the bounded original source and its physical identity.
        current_bytes, current_identity, current_status = _verified_source(candidate)
        if (
            current_status != "READY"
            or current_identity != original_identity
            or current_bytes is None
            or sha256(current_bytes).digest() != digest
        ):
            return {**base, "status": "SOURCE_CHANGED"}
        return {
            **base,
            "status": (
                "CLI_ARGV_CONTRACT_MISMATCH" if not argv_matches
                else "ADAPTERS_PARTIAL_LOAD_WARNINGS" if result.warnings
                else "ADAPTERS_VALIDATED_OFFLINE"
            ),
            "cli_argv_parity_verified": argv_matches,
            "active_m23": bool(navigation.enabled),
            "active_m25": bool(experience.enabled),
            "single_device_enforced": (
                set(experience.device_mix_dict()) == {state.device.upper()}
                if experience.enabled else None
            ),
            "load_warning_count": len(result.warnings),
            "load_warning_categories": _classify_load_warnings(result.warnings),
            "load_warning_environment_reasons": _classify_environment_warning_reasons(
                result.warnings
            ),
        }
    except (OSError, UnicodeError, ConfigError, ValueError, TypeError, OverflowError):
        return {**base, "status": "CONFIG_OR_ADAPTER_INVALID"}
    finally:
        os.environ.clear()
        os.environ.update(environment_before)
        # No global M25 pending config was changed; there is nothing to
        # reset. In particular, do not clear a pre-existing paid AUD handoff.

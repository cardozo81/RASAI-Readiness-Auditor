"""#523: detached CLI-to-consumer binding check for core AI and Web settings.

Reads an existing sealed-in-place INI into an isolated temporary copy. It
does NOT execute a CLI command, AI provider, PageSpeed, CrUX, collector or
audit. No file paths, targets, models, tokens or raw state values are
included in the returned JSON.
"""
from __future__ import annotations

from hashlib import sha256
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from rasai.console_apdex_effective_validation import _verified_source

CONTRACT = "RASAI-CONSOLE-CORE-CLI-523-001"


def inspect_core_consumers(
    ini_path: Path, *, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract": CONTRACT, "status": "NOT_VERIFIABLE",
        "typed_fields_to_cli_verified": False,
        "effective_ai_timeout_verified": False,
        "effective_ai_cycle_policy_verified": False,
        "effective_web_config_verified": False,
        "web_external_prerequisite": "NOT_EVALUATED",
        "configured_target_in_ini": False,
        "paid_provider_authorized": False,
        "physical_runtime_execution_verified": False,
        "values_exposed": False, "provider_requests": 0,
        "audit_writes": 0, "ini_source_writes": 0,
    }
    source = Path(ini_path)
    raw, identity, status = _verified_source(source)
    if status != "READY":
        return {**base, "status": status}
    assert raw is not None and identity is not None
    digest = sha256(raw).digest()
    environment_before = dict(os.environ)
    try:
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        from rasai import cli as audit_cli, console_settings, cli_extensions
        from rasai.console_config import build_command
        from rasai.console_ui_refactor import _install_search_persistence
        from rasai.console_complete_persistence import install
        from rasai.console_search_intelligence import SearchConsoleState
        from rasai.m24_cli import configured_m24
        from rasai.provider_registry import get_provider_registration

        _install_search_persistence()
        install()
        with TemporaryDirectory(prefix="rasai-core-523-") as folder:
            duplicate = Path(folder) / "detached.ini"
            duplicate.write_bytes(raw)
            state = SearchConsoleState()
            loaded = console_settings.load_console_config(state, duplicate)
            if loaded.created or loaded.warnings:
                return {**base, "status": "INI_LOAD_WARNINGS"}
            # A blank target is a valid saved PREPARAR state. Never mistake
            # a fabricated parser target for operator authorization.
            target_present = bool(str(state.target or "").strip())
            if not target_present:
                state.target = "https://example.invalid"
            console_settings.sync_nonsecret_runtime_environment(state)
            argv = build_command(state)
            parsed = cli_extensions.build_parser().parse_args(argv[3:])
            registration = get_provider_registration(str(state.ai_provider))
            expected_model = (
                state.ai_model if registration is not None and state.ai_model
                else None
            )
            comparison = {
                "target": state.target,
                "project": state.project or None,
                "language": state.language,
                "market": state.market,
                "max_pages": state.max_pages,
                "audits_root": state.audits_root,
                "device_context": state.device,
                "ai_provider": state.ai_provider,
                "ai_model": expected_model,
                "ai_content_remediation": state.content_remediation,
                "ai_technical_remediation": state.technical_remediation,
                "web_performance": state.web_performance,
            }
            cli_match = all(
                getattr(parsed, name, object()) == expected
                for name, expected in comparison.items()
            )
            effective_ai_timeout = False
            if state.ai_provider != "none":
                value = audit_cli._configured_ai_timeout_seconds()
                effective_ai_timeout = math.isclose(value, state.ai_timeout)
            # AI_TIMEOUT_ENV still traverses the runtime projection when
            # provider=none, but no provider consumes it in that scenario.
            # Check the live canonical policy constructor without executing
            # an AI need, invoking models or sleeping between cycles.
            from rasai.ai_canonical_orchestration import (
                AiExecutionPolicy, AI_MAX_CYCLES_ENV, AI_CYCLE_DELAY_ENV,
            )
            policy = AiExecutionPolicy(
                max_cycles=int(os.environ[AI_MAX_CYCLES_ENV]),
                cycle_delay_seconds=float(os.environ[AI_CYCLE_DELAY_ENV]),
            )
            ai_policy_match = (
                policy.max_cycles == state.ai_max_cycles
                and math.isclose(policy.cycle_delay_seconds, state.ai_cycle_delay)
            )
            web_state = "DISABLED"
            web_match = False
            try:
                web = audit_cli._configured_web_performance(parsed)
                if not state.web_performance:
                    web_match = not web.enabled
                else:
                    expected_categories = tuple(
                        s.strip().casefold()
                        for s in state.lighthouse_categories.split(",")
                        if s.strip()
                    )
                    web_match = (
                        web.enabled
                        and web.max_pages == state.web_max_pages
                        and math.isclose(web.timeout_seconds, state.web_timeout)
                        and web.field_source == state.field_source
                        and web.categories == expected_categories
                    )
                web_state = "NOT_REQUIRED" if state.field_source != "crux" or not state.web_performance else (
                    "PRESENT" if web.crux_api_key else "ABSENT"
                )
            except ValueError:
                # Most importantly, no fake CrUX key or paid consent is
                # invented to force a green adapter preflight.
                web_state = "UNVERIFIED"
            verified = cli_match and web_match and ai_policy_match
        checked, final_identity, final_status = _verified_source(source)
        if (final_status != "READY" or identity != final_identity
                or checked is None or sha256(checked).digest() != digest):
            return {**base, "status": "SOURCE_CHANGED"}
        return {
            **base,
            "status": (
                "CORE_CLI_PARITY_VERIFIED" if verified and target_present
                else "CLI_PARITY_TARGET_NOT_SET" if verified
                else "EXTERNAL_WEB_PREREQUISITE_UNVERIFIED"
                if cli_match and not web_match and web_state == "UNVERIFIED"
                else "CORE_CLI_CONSUMER_MISMATCH"
            ),
            "typed_fields_to_cli_verified": cli_match,
            "effective_ai_timeout_verified": effective_ai_timeout,
            "effective_ai_cycle_policy_verified": ai_policy_match,
            "effective_web_config_verified": web_match,
            "web_external_prerequisite": web_state,
            "configured_target_in_ini": target_present,
        }
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError, SystemExit):
        return {**base, "status": "INI_OR_RUNTIME_INVALID"}
    finally:
        os.environ.clear()
        os.environ.update(environment_before)


__all__ = ["inspect_core_consumers", "CONTRACT"]

"""#523: read-only typed INI-to-adapter reconciliation without replaying a console.

Checks whether the *persisted typed fields* can be parsed by the current
console adapters and projected to declared runtime environment keys. This
does NOT attest execution by M23/M25, provider calls, paid opt-in or physical
restoration in a second OS process. The operator's environment and INI are
never altered, and no value (including URL, JSON, query or path) is emitted.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from rasai.console_configuration_inventory import _ini_with_status

CONTRACT = "RASAI-CONSOLE-TYPED-RECONCILIATION-523-001"
_TYPED = frozenset({
    "console", "ai", "web_performance",
    "synthetic_apdex", "synthetic_apdex_experience",
})
_CORE_RUNTIME = {
    ("console", "device"): "RASAI_DEVICE_CONTEXT",
    ("ai", "timeout_seconds"): "RASAI_AI_TIMEOUT_SECONDS",
    ("ai", "max_cycles"): "RASAI_AI_MAX_CYCLES",
    ("ai", "cycle_delay_seconds"): "RASAI_AI_CYCLE_DELAY_SECONDS",
    ("synthetic_apdex", "enabled"): "RASAI_SYNTHETIC_APDEX",
    ("synthetic_apdex", "threshold_seconds"): "RASAI_APDEX_THRESHOLD_SECONDS",
    ("synthetic_apdex", "samples_per_context"): "RASAI_APDEX_SAMPLES_PER_CONTEXT",
    ("synthetic_apdex", "max_attempts_per_context"): "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT",
    ("synthetic_apdex", "max_pages"): "RASAI_APDEX_MAX_PAGES",
    ("synthetic_apdex", "timeout_seconds"): "RASAI_APDEX_TIMEOUT_SECONDS",
    ("synthetic_apdex", "delay_seconds"): "RASAI_APDEX_DELAY_SECONDS",
    ("synthetic_apdex", "concurrency"): "RASAI_APDEX_CONCURRENCY",
    ("synthetic_apdex_experience", "enabled"): "RASAI_APDEX_EXPERIENCE",
    ("synthetic_apdex_experience", "samples_per_page"): "RASAI_APDEX_EXPERIENCE_SAMPLES",
    ("synthetic_apdex_experience", "max_attempts_per_page"): "RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS",
    ("synthetic_apdex_experience", "max_pages"): "RASAI_APDEX_EXPERIENCE_MAX_PAGES",
    ("synthetic_apdex_experience", "session_mode"): "RASAI_APDEX_EXPERIENCE_SESSION_MODE",
    ("synthetic_apdex_experience", "architecture"): "RASAI_APDEX_EXPERIENCE_ARCHITECTURE",
    ("synthetic_apdex_experience", "profile_mode"): "RASAI_APDEX_EXPERIENCE_PROFILE_MODE",
    ("synthetic_apdex_experience", "kpm"): "RASAI_APDEX_EXPERIENCE_KPM",
    ("synthetic_apdex_experience", "satisfied_seconds"): "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS",
    ("synthetic_apdex_experience", "frustrated_seconds"): "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS",
    ("synthetic_apdex_experience", "errors_affect_apdex"): "RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT",
    ("synthetic_apdex_experience", "javascript_errors_affect_apdex"): "RASAI_APDEX_EXPERIENCE_JAVASCRIPT_ERRORS_AFFECT",
    ("synthetic_apdex_experience", "request_errors_affect_apdex"): "RASAI_APDEX_EXPERIENCE_REQUEST_ERRORS_AFFECT",
    ("synthetic_apdex_experience", "console_errors_affect_apdex"): "RASAI_APDEX_EXPERIENCE_CONSOLE_ERRORS_AFFECT",
    ("synthetic_apdex_experience", "javascript_error_capture"): "RASAI_APDEX_EXPERIENCE_JAVASCRIPT_ERROR_CAPTURE",
    ("synthetic_apdex_experience", "xhr_capture"): "RASAI_APDEX_EXPERIENCE_XHR_CAPTURE",
    ("synthetic_apdex_experience", "fetch_capture"): "RASAI_APDEX_EXPERIENCE_FETCH_CAPTURE",
    ("synthetic_apdex_experience", "console_error_capture"): "RASAI_APDEX_EXPERIENCE_CONSOLE_ERROR_CAPTURE",
    ("synthetic_apdex_experience", "max_error_details"): "RASAI_APDEX_EXPERIENCE_MAX_ERROR_DETAILS",
    ("synthetic_apdex_experience", "error_scope"): "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE",
    ("synthetic_apdex_experience", "settle_seconds"): "RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS",
    ("synthetic_apdex_experience", "delay_seconds"): "RASAI_APDEX_EXPERIENCE_DELAY_SECONDS",
    ("synthetic_apdex_experience", "concurrency"): "RASAI_APDEX_EXPERIENCE_CONCURRENCY",
    ("synthetic_apdex_experience", "dynatrace_import"): "RASAI_APDEX_DYNATRACE_IMPORT",
    ("synthetic_apdex_experience", "dynatrace_base_url"): "RASAI_DYNATRACE_BASE_URL",
    ("synthetic_apdex_experience", "dynatrace_application_id"): "RASAI_DYNATRACE_APPLICATION_ID",
    ("synthetic_apdex_experience", "dynatrace_config_json"): "RASAI_DYNATRACE_CONFIG_JSON",
}
_DERIVED = frozenset({("synthetic_apdex_experience", "device_mix")})


def inspect_typed_configuration(ini_path: Path) -> dict[str, Any]:
    """Return named adapter coverage and counts only; do not load the INI.

    Uses the existing bounded, source-identity-aware INI reader. Parsing into
    an in-memory fresh state reuses the same typed assignment adapter as boot,
    but never executes the actual loader (which can populate os.environ or
    create a missing INI). Executable/runtime attestation is explicitly false.
    """
    baseline: dict[str, Any] = {
        "contract": CONTRACT, "status": "NOT_VERIFIABLE",
        "ini_source_status": "SOURCE_NOT_INSPECTED",
        "fields": [], "counts": {},
        "values_exposed": False, "external_requests": 0, "ini_writes": 0,
        "runtime_consumption_verified": False,
        "actual_boot_roundtrip_verified": False,
        "new_audit_consent_inherited": False,
    }
    try:
        parser, status = _ini_with_status(Path(ini_path))
    except (OSError, TypeError, ValueError):
        return baseline
    if parser is None:
        return {**baseline, "ini_source_status": status}
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install as install_complete_persistence
    from rasai import console_settings

    _install_search_persistence()
    install_complete_persistence()
    state = SearchConsoleState()
    current = console_settings._state_values(state)
    entries: list[dict[str, str | bool | None]] = []
    for section in current:
        if section not in _TYPED:
            continue
        physical = parser._sections.get(section, {})
        for option in current[section]:
            identifier = f"{section}.{option}"
            key = (section, option)
            if key in _DERIVED:
                kind = "DERIVED_FROM_DEVICE"
            elif option not in physical:
                kind = "NOT_PERSISTED"
            elif section == "console" and option == "config_version":
                kind = "METADATA_NOT_RUNTIME_INPUT"
            else:
                try:
                    # The state is a detached object. Do not assign presentation
                    # timezone: that adapter writes os.environ.
                    console_settings._assign(state, section, option, physical[option])
                except (ValueError, TypeError, OverflowError):
                    kind = "INVALID_TYPED_VALUE"
                else:
                    kind = "ADAPTER_PARSED"
            entries.append({
                "field": identifier, "state": kind,
                "source": "INI" if option in physical else "NOT_IN_INI",
                "runtime_projection_key": _CORE_RUNTIME.get(key),
                "runtime_input_proven": False,
            })
        unrecognized = set(physical) - set(current[section])
        if unrecognized:
            entries.append({
                "field": section + ".[unrecognized-fields]",
                "state": "UNRECOGNIZED_INPUT_COUNT",
                "source": "INI",
                "runtime_projection_key": None, "runtime_input_proven": False,
                "count": len(unrecognized),
            })
    # The adapter's runtime projection is a second, independent contract.
    # Being syntactically projected is not proof of M23/M25 subprocess argv.
    try:
        projected = console_settings._runtime_environment_projection(state)
    except (ValueError, TypeError, OverflowError):
        projected = {}
    for entry in entries:
        if entry["state"] != "ADAPTER_PARSED":
            continue
        key = entry["runtime_projection_key"]
        if key is not None:
            entry["state"] = (
                "DECLARED_RUNTIME_PROJECTION"
                if str(projected.get(key, "")).strip() else (
                    "RUNTIME_PROJECTION_EMPTY" if key in projected
                    else "RUNTIME_PROJECTION_ABSENT"
                )
            )
    counts = dict(sorted(Counter(item["state"] for item in entries).items()))
    return {
        **baseline,
        "status": "TYPED_ADAPTERS_INSPECTED",
        "ini_source_status": status,
        "fields": entries,
        "counts": counts,
        "fields_inspected": len(entries),
        "invalid_typed_fields": counts.get("INVALID_TYPED_VALUE", 0),
        "projected_fields_are_execution_proof": False,
    }


__all__ = ["inspect_typed_configuration", "CONTRACT"]

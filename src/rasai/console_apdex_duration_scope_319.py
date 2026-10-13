"""#319: descriptive, non-secret Apdex workload fingerprint for console duration.

This module neither configures nor invokes M23/M25; it only captures
pre-existing state fields in the post-run console execution projection.
A matching fingerprint is necessary, never sufficient, for a comparable
duration cohort. None of the recorded values proves physical sample counts.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


NAVIGATION_FIELDS = (
    "apdex_threshold", "apdex_samples", "apdex_max_attempts",
    "apdex_max_pages", "apdex_timeout", "apdex_delay", "apdex_concurrency",
)
EXPERIENCE_FIELDS = (
    "apdex_experience_samples", "apdex_experience_max_attempts",
    "apdex_experience_max_pages", "apdex_experience_device_mix",
    "apdex_experience_session_mode", "apdex_experience_kpm",
    "apdex_experience_architecture", "apdex_experience_profile_mode",
    "apdex_experience_satisfied", "apdex_experience_frustrated",
    "apdex_experience_errors", "apdex_experience_javascript_errors",
    "apdex_experience_request_errors", "apdex_experience_console_errors",
    "apdex_experience_javascript_capture", "apdex_experience_xhr_capture",
    "apdex_experience_fetch_capture", "apdex_experience_console_capture",
    "apdex_experience_max_error_details", "apdex_experience_error_scope",
    "apdex_experience_settle", "apdex_experience_delay",
    "apdex_experience_concurrency", "apdex_dynatrace_import",
)
_MODULES = (
    ("synthetic_apdex", "synthetic_apdex_workload", NAVIGATION_FIELDS),
    ("apdex_experience", "apdex_experience_workload", EXPERIENCE_FIELDS),
)


def _primitive(value: Any) -> bool:
    if value is None:
        return True
    if type(value) in (str, int, bool):
        return True
    return type(value) is float and math.isfinite(value)


def _fields_from_state(state: Any, names: tuple[str, ...]) -> dict[str, Any] | None:
    selected: dict[str, Any] = {}
    for field in names:
        if not hasattr(state, field):
            return None
        value = getattr(state, field)
        if not _primitive(value):
            return None
        selected[field] = value
    return selected


def apdex_duration_scope(state: Any) -> dict[str, Any]:
    """Snapshot flags and, for enabled modules, safe workload parameters.

    Never persist Dynatrace token, base URL, application ID, config JSON,
    browser contents or provider credentials. For incomplete/invalid
    state, record the active flag without a workload fingerprint; a
    future duration predictor will reject it rather than extrapolate.
    """
    output: dict[str, Any] = {}
    for flag, workload_key, fields in _MODULES:
        enabled = getattr(state, flag, False)
        if type(enabled) is not bool:
            continue
        output[flag] = enabled
        if enabled:
            scope = _fields_from_state(state, fields)
            if scope is not None:
                output[workload_key] = scope
    return output


def comparable_apdex_duration_scope(
    state: Any, historical: Mapping[str, Any],
) -> bool:
    """Require exact typed parameter identity for an active Apdex module."""
    for flag, workload_key, fields in _MODULES:
        current_enabled = getattr(state, flag, False)
        if type(current_enabled) is not bool:
            return False
        saved_enabled = historical.get(flag)
        if flag not in historical:
            if current_enabled:
                return False
        elif type(saved_enabled) is not bool or saved_enabled != current_enabled:
            return False
        if not current_enabled:
            continue
        wanted = _fields_from_state(state, fields)
        recorded = historical.get(workload_key)
        if wanted is None or not isinstance(recorded, dict):
            return False
        if set(recorded) != set(fields):
            return False
        for name, current in wanted.items():
            old = recorded[name]
            if not _primitive(old) or type(current) is not type(old) or current != old:
                return False
    return True

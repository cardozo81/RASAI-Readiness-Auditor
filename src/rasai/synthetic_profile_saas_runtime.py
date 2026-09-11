"""SaaS/control-plane integration for synthetic runtime profile presets.

The durable audit job stores only non-secret preset identifiers. Workers resolve those
identifiers through the same catalog used by the local console and project them into
environment variables consumed by the synthetic browser runtime.
"""
from __future__ import annotations

from typing import Any, Mapping

from rasai.synthetic_runtime_profiles import (
    default_preset,
    env_name,
    preset_ids,
    validate_preset,
)

_INSTALLED = False

PROFILE_PAYLOAD_FIELDS: dict[str, tuple[str, str]] = {
    "apdex_mobile_client_profile": ("MOBILE", "client"),
    "apdex_mobile_hardware_profile": ("MOBILE", "hardware"),
    "apdex_mobile_network_profile": ("MOBILE", "network"),
    "apdex_desktop_client_profile": ("DESKTOP", "client"),
    "apdex_desktop_hardware_profile": ("DESKTOP", "hardware"),
    "apdex_desktop_network_profile": ("DESKTOP", "network"),
    "apdex_tablet_client_profile": ("TABLET", "client"),
    "apdex_tablet_hardware_profile": ("TABLET", "hardware"),
    "apdex_tablet_network_profile": ("TABLET", "network"),
}


def normalized_runtime_profiles(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Return validated profile identifiers grouped by device."""
    result = {device: {} for device in ("MOBILE", "DESKTOP", "TABLET")}
    for field, (device, kind) in PROFILE_PAYLOAD_FIELDS.items():
        raw = payload.get(field, default_preset(kind, device))
        if not isinstance(raw, str):
            raise ValueError(f"AUDIT payload field {field} must be text")
        result[device][kind] = validate_preset(kind, device, raw)
    return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_execution_contract as contract

    original_options = contract.audit_job_options
    original_defaults = contract.audit_job_defaults
    original_normalize = contract.normalize_audit_job_payload
    original_environment = contract.audit_job_environment_overrides
    base_fields = frozenset(contract.AUDIT_JOB_FIELDS)

    contract.AUDIT_JOB_FIELDS = frozenset((*base_fields, *PROFILE_PAYLOAD_FIELDS.keys()))

    def options_with_profiles():
        values = list(original_options())
        known = {item.name for item in values}
        for field, (device, kind) in PROFILE_PAYLOAD_FIELDS.items():
            if field in known:
                continue
            values.append(
                contract.AuditJobOption(
                    field,
                    default_preset(kind, device),
                    "enum",
                    preset_ids(kind, device),
                    description=(
                        f"Perfil sintético {kind} para {device}; controla somente a condição de laboratório "
                        "e não altera a fórmula Apdex."
                    ),
                )
            )
        return tuple(values)

    def defaults_with_profiles() -> dict[str, Any]:
        values = dict(original_defaults())
        for field, (device, kind) in PROFILE_PAYLOAD_FIELDS.items():
            values[field] = default_preset(kind, device)
        return values

    def normalize_with_profiles(payload: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(payload) - contract.AUDIT_JOB_FIELDS)
        if unknown:
            raise ValueError("unsupported AUDIT execution payload field(s): " + ", ".join(unknown))
        base_payload = {key: value for key, value in payload.items() if key not in PROFILE_PAYLOAD_FIELDS}
        normalized = dict(original_normalize(base_payload))
        for field, (device, kind) in PROFILE_PAYLOAD_FIELDS.items():
            raw = payload.get(field, default_preset(kind, device))
            if not isinstance(raw, str):
                raise ValueError(f"AUDIT payload field {field} must be text")
            normalized[field] = validate_preset(kind, device, raw)
        return normalized

    def environment_with_profiles(payload: Mapping[str, Any]) -> dict[str, str]:
        base_payload = {key: value for key, value in payload.items() if key not in PROFILE_PAYLOAD_FIELDS}
        overrides = dict(original_environment(base_payload))
        normalized = normalize_with_profiles(payload)
        for field, (device, kind) in PROFILE_PAYLOAD_FIELDS.items():
            overrides[env_name(kind, device)] = str(normalized[field])
        return overrides

    contract.audit_job_options = options_with_profiles
    contract.audit_job_defaults = defaults_with_profiles
    contract.normalize_audit_job_payload = normalize_with_profiles
    contract.audit_job_environment_overrides = environment_with_profiles
    contract._rasai_synthetic_profile_saas = True

    # Several execution surfaces import contract callables by value. Synchronize any
    # already imported modules so direct API/worker entrypoints observe the same job
    # schema and validation without depending on import order.
    try:
        from rasai import execution_contract
        if getattr(execution_contract, "normalize_audit_job_payload", None) is original_normalize:
            execution_contract.normalize_audit_job_payload = normalize_with_profiles
    except Exception:
        pass

    try:
        from rasai import worker
        if getattr(worker, "normalize_audit_job_payload", None) is original_normalize:
            worker.normalize_audit_job_payload = normalize_with_profiles
        if getattr(worker, "audit_job_environment_overrides", None) is original_environment:
            worker.audit_job_environment_overrides = environment_with_profiles
    except Exception:
        pass

    try:
        from rasai.web import saas_management_routes
        if getattr(saas_management_routes, "audit_job_options", None) is original_options:
            saas_management_routes.audit_job_options = options_with_profiles
    except Exception:
        pass

    _INSTALLED = True

"""#358: pure architecture-sensitive M25 guidance, never an Apdex engine.

M6 architecture becomes available after capture. A reported observation is not
permission to alter a frozen AUD config, create an XHR synthetic action, or
derive a content-ready duration from navigation load.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import math

from rasai.m25_dynatrace_defaults import (
    DYNATRACE_REFERENCE_PROFILE,
    DYNATRACE_REFERENCE_URLS,
    RASAI_DYNATRACE_COMPAT_KPM,
    RASAI_DYNATRACE_COMPAT_SATISFIED_SECONDS,
    RASAI_DYNATRACE_COMPAT_FRUSTRATED_SECONDS,
)

VERSION = "RASAI-CAT07-ARCHITECTURE-GUIDANCE-001"
ARCHITECTURES = frozenset({
    "AUTO", "STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN",
})
MODES = frozenset({"DYNATRACE_GUIDED", "CUSTOM", "DYNATRACE_IMPORTED"})
_EXECUTABLE_KPMS = frozenset({
    "USER_ACTION_DURATION", "DOM_INTERACTIVE", "LOAD_EVENT_START",
    "LOAD_EVENT_END", "RESPONSE_START", "RESPONSE_END",
    "LARGEST_CONTENTFUL_PAINT",
})
_VARS = (
    ("kpm", "RASAI_APDEX_EXPERIENCE_KPM"),
    ("satisfied_threshold_seconds", "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS"),
    ("frustrated_threshold_seconds", "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS"),
)
# Only public non-secret fields from the persisted *effective* M25 run.
# Do not infer defaults from the current host/INI or import configuration blobs.
RECORDED_POLICY_FIELDS = (
    "errors_affect_apdex",
    "javascript_errors_affect_apdex",
    "request_errors_affect_apdex",
    "console_errors_affect_apdex",
    "javascript_error_capture",
    "xhr_capture",
    "fetch_capture",
    "console_error_capture",
)
RECORDED_SCOPE_FIELDS = (
    "error_scope", "session_mode", "target_samples_per_page",
    "max_attempts_per_page", "concurrency", "settle_seconds", "delay_seconds",
)
RECORDED_CONTEXT_FIELDS = RECORDED_POLICY_FIELDS + RECORDED_SCOPE_FIELDS


def _recorded_run_context(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Whitelist effective settings, invalid/missing/legacy values remain None."""
    if not isinstance(config, Mapping):
        config = {}
    result: dict[str, Any] = {}
    for key in RECORDED_CONTEXT_FIELDS:
        value = config.get(key)
        if key in RECORDED_POLICY_FIELDS:
            valid = type(value) is bool
        elif key == "error_scope":
            valid = isinstance(value, str) and value in {"navigation", "first-party", "all"}
        elif key == "session_mode":
            valid = isinstance(value, str) and value in {"cold", "warm"}
        elif key in {"target_samples_per_page", "max_attempts_per_page", "concurrency"}:
            valid = type(value) is int and 1 <= value <= 1000000
            if key == "concurrency":
                valid = type(value) is int and 1 <= value <= 3
        else:
            valid = (
                type(value) in (int, float) and math.isfinite(value)
                and 0 <= value <= 24 * 3600
                and (key != "settle_seconds" or value > 0)
            )
        result[key] = value if valid else None
    return result


_NOTICE_BY_ARCH = {
    "STATIC_OR_SSR": (
        "Load Action pode representar navegação completa do documento; "
        "não comprova prontidão ou interatividade."
    ),
    "CSR_SPA": (
        "Load Action cobre a entrada inicial. Soft navigations XHR/Fetch "
        "não são medidas como ações autônomas pelo M25."
    ),
    "HYDRATED": (
        "O HTML inicial pode anteceder a hidratação/interatividade. "
        "Load não demonstra prontidão interativa."
    ),
    "MIXED": (
        "Load pode cobrir apenas parte das rotas/seções; "
        "não presume uma única arquitetura para a aplicação."
    ),
    "UNKNOWN": "Arquitetura não comprovada; recomendação por classe N/D.",
    "AUTO": "Arquitetura não identificada na configuração prévia; o padrão do RASAi não equivale à classificação M6.",
}


def _duration(value: object) -> bool:
    return (
        type(value) in (int, float) and math.isfinite(value)
        and 0 < value <= 24 * 3600
    )


def _safe_arch(value: object, *, allow_auto: bool) -> str:
    if not isinstance(value, str):
        return "UNKNOWN"
    proposed = value.strip().upper()
    return proposed if proposed in ARCHITECTURES and (allow_auto or proposed != "AUTO") else "UNKNOWN"


def _safe_config(config: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Only stated effective executable fields; missing fields remain N/D."""
    supplied = {
        key: config.get(key) for key, _ in _VARS
    }
    bad: list[str] = []
    kpm = supplied["kpm"]
    if kpm is not None and (not isinstance(kpm, str) or kpm not in _EXECUTABLE_KPMS):
        bad.append("KPM_NOT_EXECUTABLE_IN_M25")
    satisfied = supplied["satisfied_threshold_seconds"]
    frustrated = supplied["frustrated_threshold_seconds"]
    if satisfied is not None and not _duration(satisfied):
        bad.append("SATISFIED_INVALID")
    if frustrated is not None and not _duration(frustrated):
        bad.append("FRUSTRATED_INVALID")
    if _duration(satisfied) and _duration(frustrated) and frustrated <= satisfied:
        bad.append("FRUSTRATED_NOT_GREATER_THAN_SATISFIED")
    return supplied, tuple(bad)


def resolve_experience_architecture_guidance(
    config: Mapping[str, Any] | None, *,
    selected_architecture: str = "AUTO",
    observed_architecture: str | None = None,
    provenance: Mapping[str, Any] | None = None,
    profile_mode: str = "CUSTOM",
    objective: str = "INITIAL_LOAD",
    per_field_source: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return an advisory and explicit *proposed* settings, never mutate input.

    selected_architecture is an OPERATOR declaration before the audit.
    observed_architecture is an M6 classification only if page/snapshot/device
    provenance is supplied. Neither can change the already-measured M25.
    """
    declared = _safe_arch(selected_architecture, allow_auto=True)
    verified_snapshot = (
        isinstance(provenance, Mapping)
        and all(
            isinstance(provenance.get(key), str)
            and bool(provenance[key].strip())
            for key in ("snapshot_id", "page_id", "device")
        )
    )
    observed = (
        _safe_arch(observed_architecture, allow_auto=False)
        if verified_snapshot else "UNKNOWN"
    )
    effective_arch = observed if observed != "UNKNOWN" else declared
    if effective_arch == "AUTO":
        effective_arch = "UNKNOWN"
    mode = profile_mode if profile_mode in MODES else "UNKNOWN"
    source = (
        "M6_OBSERVED" if observed != "UNKNOWN"
        else "OPERATOR_DECLARED" if declared not in {"AUTO", "UNKNOWN"}
        else "UNKNOWN"
    )
    divergence = (
        observed != "UNKNOWN" and declared not in {"AUTO", "UNKNOWN"}
        and observed != declared
    )
    values, invalid = _safe_config(config) if isinstance(config, Mapping) else (
        {key: None for key, _ in _VARS},
        ("EFFECTIVE_CONFIG_NOT_AVAILABLE",),
    )
    field_sources = {
        key: (
            str(per_field_source[key])[:100]
            if isinstance(per_field_source, Mapping)
            and isinstance(per_field_source.get(key), str)
            and per_field_source[key].strip()
            else "UNVERIFIED"
        )
        for key, _ in _VARS
    }
    proposed = {
        "kpm": RASAI_DYNATRACE_COMPAT_KPM,
        "satisfied_threshold_seconds": RASAI_DYNATRACE_COMPAT_SATISFIED_SECONDS,
        "frustrated_threshold_seconds": RASAI_DYNATRACE_COMPAT_FRUSTRATED_SECONDS,
    }
    reasons = list(invalid)
    next_actions = []
    if divergence:
        reasons.append("DECLARED_VS_OBSERVED_ARCHITECTURE_MISMATCH")
        next_actions.append({
            "scope": "RASAI_EXECUTABLE_NOW",
            "text": "Conferir a classificação M6 e a arquitetura declarada por URL/dispositivo antes de uma nova AUD.",
        })
    if mode == "UNKNOWN":
        reasons.append("PROFILE_MODE_NOT_RECOGNIZED")
    if mode == "DYNATRACE_IMPORTED" and not isinstance(config, Mapping):
        reasons.append("IMPORTED_CONFIG_PROVENANCE_UNAVAILABLE")
    if effective_arch == "UNKNOWN":
        reasons.append("ARCHITECTURE_NOT_PROVEN")
    if objective not in {"INITIAL_LOAD", "WIDER_EXPERIENCE"}:
        reasons.append("MEASUREMENT_OBJECTIVE_NOT_PROVEN")
    wider = objective == "WIDER_EXPERIENCE"
    if wider and effective_arch in {"CSR_SPA", "HYDRATED", "MIXED"}:
        reasons.append("INITIAL_LOAD_DOES_NOT_COVER_WIDER_EXPERIENCE")
        next_actions.append({
            "scope": "DYNATRACE_EXTERNAL",
            "text": "Avaliar XHR/navegação suave, ações personalizadas e interatividade em RUM; o M25 não executa essas ações autonomamente.",
        })
    next_actions.append({
        "scope": "FUTURE_CAPABILITY",
        "text": "A prontidão real do conteúdo na mesma amostra exige a validação física #322.",
    })
    differences = {
        key: {"effective": values.get(key), "guided": proposed[key],
              "current_origin": field_sources[key]}
        for key, _ in _VARS
        if values.get(key) is not None and values.get(key) != proposed[key]
    }
    preview: list[dict[str, Any]] = []
    if mode == "DYNATRACE_GUIDED":
        for key, name in _VARS:
            preview.append({
                "variable": name,
                "value": str(proposed[key]),
                "source": "RASAI_EXECUTABLE_DYNATRACE_LOAD_FALLBACK_REFERENCE",
                "action": "PROPOSE_ONLY_REQUIRES_OPERATOR_CONFIRMATION",
                "would_override_current": key in differences,
            })
        if differences:
            reasons.append("GUIDED_PRESET_CONFLICTS_WITH_EFFECTIVE_FIELDS")
        next_actions.append({
            "scope": "RASAI_EXECUTABLE_NOW",
            "text": "Aprovar explicitamente os parâmetros guiados ou manter a configuração atual; não alterar amostras, dispositivo ou políticas de carga.",
        })
    if mode == "DYNATRACE_IMPORTED":
        next_actions.append({
            "scope": "RASAI_EXECUTABLE_NOW",
            "text": "Preservar o analisador e a precedência da importação atual; indicar alternativa somente quando comprovada no registro de calibração.",
        })
    if mode == "CUSTOM":
        next_actions.append({
            "scope": "RASAI_EXECUTABLE_NOW",
            "text": "Manter valores explícitos do operador; validar domínios e origem por campo sem sobrescrever com a predefinição.",
        })
    adequate_scope = (
        not invalid and mode != "UNKNOWN"
        and values["kpm"] in _EXECUTABLE_KPMS
        and _duration(values["satisfied_threshold_seconds"])
        and _duration(values["frustrated_threshold_seconds"])
    )
    if divergence or (mode == "DYNATRACE_GUIDED" and differences):
        adequacy = "REVISAO_RECOMENDADA"
    elif effective_arch == "UNKNOWN" or not adequate_scope:
        adequacy = "INDETERMINADA"
    elif wider and effective_arch in {"CSR_SPA", "HYDRATED", "MIXED"}:
        adequacy = "COBERTURA_PARCIAL"
    else:
        adequacy = "ADEQUADA_AO_ESCOPO"
    return {
        "contract_version": VERSION,
        "architecture_source": source,
        "selected_architecture": declared,
        "observed_architecture": observed,
        "effective_architecture_for_advice": effective_arch,
        "observed_snapshot_provenance": (
            {key: provenance[key] for key in ("snapshot_id", "page_id", "device")}
            if observed != "UNKNOWN" and verified_snapshot else None
        ),
        "architecture_mismatch": divergence,
        "profile_mode": mode,
        "profile_version": DYNATRACE_REFERENCE_PROFILE if mode == "DYNATRACE_GUIDED" else None,
        "reference_doc_urls": DYNATRACE_REFERENCE_URLS,
        "requested_kpm": values.get("kpm"),
        "effective_kpm": values.get("kpm"),
        "effective_settings": values,
        "effective_recorded_run_context": _recorded_run_context(config),
        "recorded_run_context_origin": "PERSISTED_EFFECTIVE_M25_CONFIGURATION_ONLY",
        "per_field_source": field_sources,
        "fallback_reason": None,
        "objective": objective,
        "measured_task": "SYNTHETIC_LOAD_ACTION",
        "available_action_types": ["LOAD"],
        "unsupported_action_types": ["XHR_AUTONOMOUS", "CUSTOM_AUTONOMOUS", "VENDOR_VISUALLY_COMPLETE"],
        "adequacy": adequacy,
        "reasons": reasons,
        "architecture_limitations": _NOTICE_BY_ARCH[effective_arch],
        "next_actions": next_actions,
        "new_audit_configuration_preview": preview,
        "new_audit_started": False,
        "synthetic_apdex_changed": False,
        "original_aud_writes": 0,
        "provider_requests": 0,
    }

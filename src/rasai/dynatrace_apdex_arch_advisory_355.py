"""#355: read-only Dynatrace RUM Apdex architecture/configuration advisory.

RUM Load, XHR and Custom actions are different populations. A SPA may
legitimately have an initial Load action AND subsequent XHR route actions.
Do not import or change the homologated RASAi synthetic M23/M25 engines.
No Dynatrace HTTP client, secret, provider, scoring, database or report write.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

VERSION = "RASAI-DYNATRACE-APDEX-ARCHITECTURE-ADVISORY-001"
ARCHITECTURES = frozenset({
    "CSR_SPA", "HYDRATED", "MIXED", "STATIC_OR_SSR", "UNKNOWN",
})
KPM_BY_ACTION = {
    "load_actions": frozenset({
        "USER_ACTION_DURATION", "VISUALLY_COMPLETE", "SPEED_INDEX",
        "DOM_INTERACTIVE", "LOAD_EVENT_END", "LOAD_EVENT_START",
        "RESPONSE_END", "RESPONSE_START", "FIRST_INPUT_DELAY",
        "LARGEST_CONTENTFUL_PAINT", "CUMULATIVE_LAYOUT_SHIFT",
    }),
    "xhr_actions": frozenset({
        "USER_ACTION_DURATION", "VISUALLY_COMPLETE",
        "RESPONSE_END", "RESPONSE_START",
    }),
    "custom_actions": frozenset({"USER_ACTION_DURATION"}),
}
_MAIN_THRESHOLD_KEYS = ("toleratedThresholdSeconds", "frustratingThresholdSeconds")
_FALLBACK_KEYS = (
    "toleratedFallbackThresholdSeconds", "frustratingFallbackThresholdSeconds",
)


def _valid_limits(value: object, keys: tuple[str, str]) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        first, last = (value[k] for k in keys)
    except KeyError:
        return False
    return (
        type(first) in (int, float) and type(last) in (int, float)
        and math.isfinite(first) and math.isfinite(last)
        and 0 < first < last
    )


def _validate_settings(value: Mapping[str, Any]) -> tuple[str, ...]:
    failures = []
    for key, valid_metrics in KPM_BY_ACTION.items():
        if key not in value:
            continue  # absent does not prove a disabled Dynatrace action type
        category = value[key]
        if not isinstance(category, Mapping):
            failures.append(key + ":INVALID_ACTION_CONFIGURATION")
            continue
        metric = category.get("kpm", "USER_ACTION_DURATION" if key == "custom_actions" else None)
        if not isinstance(metric, str) or metric not in valid_metrics:
            failures.append(key + ":KPM_NOT_SUPPORTED_FOR_ACTION_TYPE")
        if not _valid_limits(category.get("thresholds"), _MAIN_THRESHOLD_KEYS):
            failures.append(key + ":INVALID_APDEX_THRESHOLDS")
        if key in {"load_actions", "xhr_actions"} and not _valid_limits(
            category.get("fallbackThresholds"), _FALLBACK_KEYS
        ):
            failures.append(key + ":INVALID_FALLBACK_THRESHOLDS")
    capture = value.get("capture")
    if capture is not None and (
        not isinstance(capture, Mapping)
        or any(
            key in capture and type(capture[key]) is not bool
            for key in ("xhr", "fetch")
        )
    ):
        failures.append("capture:INVALID_ASYNC_CAPTURE_FLAGS")
    counts = value.get("action_counts")
    if counts is not None and (
        not isinstance(counts, Mapping)
        or any(
            key in counts
            and (type(counts[key]) is not int or counts[key] < 0)
            for key in ("load", "xhr", "custom")
        )
    ):
        failures.append("action_counts:INVALID_POPULATION")
    return tuple(failures)


def assess_dynatrace_apdex_architecture(
    *,
    architecture: str,
    architecture_evidence_id: str | None,
    soft_navigation_observed: bool | None,
    async_requests_observed: bool | None,
    settings: Mapping[str, Any] | None,
) -> dict:
    """Explain action coverage; NEVER prescribe universal numeric thresholds.

    The caller supplies a *declared* Dynatrace settings snapshot. This adapter
    cannot certify it was actually read from that account or represents the
    same page/session as the RASAi architecture observation.
    """
    output = {
        "contract_version": VERSION,
        "architecture": architecture,
        "architecture_evidence_id": architecture_evidence_id,
        "settings_provenance": "NOT_VERIFIED_BY_RASAI",
        "method": "EXTERNAL_RUM_CONFIG_ADVISORY_NOT_SYNTHETIC_APDEX",
        "status": "NOT_EVALUABLE",
        "reasons": [],
        "review_actions": [],
        "observed_kpm": {},
        "recommended_numeric_thresholds": None,
        "new_apdex_score": None,
        "measurement_in_same_browser_sample_proven": False,
        "dynatrace_provider_requests": 0,
        "audit_writes": 0,
        "synthetic_m23_m25_changed": False,
    }
    if architecture not in ARCHITECTURES or architecture == "UNKNOWN":
        output["reasons"].append("ARCHITECTURE_NOT_PROVEN")
        return output
    if not isinstance(architecture_evidence_id, str) or not architecture_evidence_id.strip():
        output["reasons"].append("ARCHITECTURE_EVIDENCE_NOT_VERIFIED")
        return output
    if type(soft_navigation_observed) not in (bool, type(None)) or type(
        async_requests_observed
    ) not in (bool, type(None)):
        output["reasons"].append("INVALID_OBSERVATION_FLAGS")
        return output
    if not isinstance(settings, Mapping):
        output["reasons"].append("NO_DYNATRACE_SETTINGS_SNAPSHOT")
        return output
    invalid = _validate_settings(settings)
    if invalid:
        output["status"] = "INVALID_SETTINGS_SNAPSHOT"
        output["reasons"].extend(invalid)
        return output
    output["observed_kpm"] = {
        category: cfg.get("kpm", "USER_ACTION_DURATION")
        for category, cfg in settings.items()
        if category in KPM_BY_ACTION and isinstance(cfg, Mapping)
    }
    if not output["observed_kpm"]:
        output["reasons"].append("NO_ACTION_APDEX_CONFIGURATIONS")
        return output
    if architecture == "STATIC_OR_SSR" and soft_navigation_observed is False:
        if "load_actions" in settings:
            output["status"] = "CONFIGURATION_PLAUSIBLE_FOR_DOCUMENT_NAVIGATION"
            output["review_actions"].append(
                "Confirmar cobertura real de Load actions, tipos de navegação "
                "e limiares de Apdex conforme objetivos de experiência."
            )
        else:
            output["status"] = "INSUFFICIENT_ACTION_SCOPE"
            output["reasons"].append("LOAD_ACTION_CONFIGURATION_NOT_PROVIDED")
        return output
    if soft_navigation_observed is not True:
        output["status"] = "INSUFFICIENT_ACTION_SCOPE"
        output["reasons"].append("SOFT_NAVIGATION_NOT_PROVEN")
        return output
    # SPA / hydrated / mixed soft routes are a different action population.
    # Even valid initial Load configuration cannot measure every subsequent
    # route; do not replace Load globally or assume XHR if no async occurred.
    if async_requests_observed is not True:
        output["status"] = "INSUFFICIENT_ACTION_SCOPE"
        output["reasons"].append("ASYNC_TRIGGER_FOR_SOFT_NAVIGATION_NOT_PROVEN")
        output["review_actions"].append(
            "Verificar se a transição precisa de XHR/Fetch ou de ação customizada; "
            "o carregamento inicial não representa toda interação SPA."
        )
        return output
    capture = settings.get("capture", {})
    coverage = settings.get("action_counts", {})
    if (
        isinstance(capture, Mapping)
        and capture.get("xhr") is False and capture.get("fetch") is False
    ):
        output["status"] = "REVIEW_RECOMMENDED"
        output["reasons"].append("ASYNC_CAPTURE_DISABLED_FOR_OBSERVED_SOFT_NAVIGATION")
    elif isinstance(coverage, Mapping) and coverage.get("xhr") == 0:
        output["status"] = "REVIEW_RECOMMENDED"
        output["reasons"].append("NO_XHR_ACTIONS_IN_DECLARED_RUM_POPULATION")
    elif "xhr_actions" not in settings:
        output["status"] = "INSUFFICIENT_ACTION_SCOPE"
        output["reasons"].append("XHR_APDEX_CONFIGURATION_NOT_PROVIDED")
    else:
        output["status"] = "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE"
    output["review_actions"].append(
        "Revisar captura XHR/Fetch, cobertura por ação e KPM de Load vs XHR; "
        "comparar tolerating/frustrating e fallbackThresholds com SLOs reais. "
        "Nenhuma regra universal define thresholds só por ser SPA."
    )
    return output

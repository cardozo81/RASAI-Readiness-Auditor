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
        # KPM semantics may be fixed by Dynatrace for Custom actions, but
        # an absent field is not an observed configured value in this export.
        metric = category.get("kpm")
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
        "soft_navigation_observed": soft_navigation_observed,
        "async_requests_observed": async_requests_observed,
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
        category: cfg["kpm"]
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
    elif not isinstance(coverage, Mapping) or not (
        type(coverage.get("xhr")) is int and coverage["xhr"] > 0
    ):
        output["status"] = "INSUFFICIENT_ACTION_SCOPE"
        output["reasons"].append("XHR_ACTION_POPULATION_NOT_PROVEN")
    else:
        output["status"] = "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE"
    output["review_actions"].append(
        "Revisar captura XHR/Fetch, cobertura por ação e KPM de Load vs XHR; "
        "comparar tolerating/frustrating e fallbackThresholds com SLOs reais. "
        "Nenhuma regra universal define thresholds só por ser SPA."
    )
    return output


# A user-facing interpretation of the same, explicitly unverified offline verdict.
# Never translate an absent RUM setting into a claim that capture was disabled.
_STATUS_PT_BR = {
    "NOT_EVALUABLE": "Diagnóstico não determinável com as evidências fornecidas",
    "INVALID_SETTINGS_SNAPSHOT": "Configuração fornecida inconsistente ou inválida",
    "INSUFFICIENT_ACTION_SCOPE": "Cobertura das ações não comprovada",
    "REVIEW_RECOMMENDED": "Revisão de instrumentação e cobertura recomendada",
    "CONFIGURATION_PLAUSIBLE_FOR_DOCUMENT_NAVIGATION":
        "Configuração Load plausível para navegação de documento; cobertura não homologada",
    "CONFIGURATION_PLAUSIBLE_WITH_XHR_COVERAGE":
        "Configuração e população XHR declaradas plausíveis; correlação não homologada",
}
_REASON_PT_BR = {
    "ARCHITECTURE_NOT_PROVEN": "Arquitetura não determinada",
    "ARCHITECTURE_EVIDENCE_NOT_VERIFIED": "Identificador de evidência de arquitetura ausente",
    "INVALID_OBSERVATION_FLAGS": "Indicadores de navegação inválidos",
    "NO_DYNATRACE_SETTINGS_SNAPSHOT": "Nenhuma configuração RUM fornecida",
    "NO_ACTION_APDEX_CONFIGURATIONS": "Nenhuma configuração de Apdex por tipo de ação fornecida",
    "LOAD_ACTION_CONFIGURATION_NOT_PROVIDED": "Configuração Load não fornecida",
    "SOFT_NAVIGATION_NOT_PROVEN": "Transição de rota client-side não comprovada",
    "ASYNC_TRIGGER_FOR_SOFT_NAVIGATION_NOT_PROVEN":
        "XHR/Fetch na transição de rota não comprovado",
    "ASYNC_CAPTURE_DISABLED_FOR_OBSERVED_SOFT_NAVIGATION":
        "O JSON informa captura XHR e Fetch desabilitada na transição declarada",
    "NO_XHR_ACTIONS_IN_DECLARED_RUM_POPULATION":
        "O JSON informa população de XHR actions igual a zero",
    "XHR_APDEX_CONFIGURATION_NOT_PROVIDED":
        "Configuração de Apdex XHR não fornecida",
    "XHR_ACTION_POPULATION_NOT_PROVEN":
        "Quantidade de XHR actions não comprovada",
    "INVALID_ACTION_CONFIGURATION": "Configuração de ação inválida",
    "KPM_NOT_SUPPORTED_FOR_ACTION_TYPE": "KPM incompatível com o tipo de ação",
    "INVALID_APDEX_THRESHOLDS": "Thresholds Apdex inválidos",
    "INVALID_FALLBACK_THRESHOLDS": "Thresholds de fallback inválidos",
    "INVALID_ASYNC_CAPTURE_FLAGS": "Indicadores de captura inválidos",
    "INVALID_POPULATION": "Contagens de ações inválidas",
}



def _architecture_action_review(result: Mapping[str, Any]) -> dict[str, Any]:
    """Contextual Dynatrace KPM *options*, not applied settings or defaults.

    A SPA does not eliminate the initial Load action. No KPM or numeric
    threshold can be prescribed from architecture alone.
    """
    architecture = result.get("architecture")
    observed = result.get("observed_kpm")
    configured = observed if isinstance(observed, Mapping) else {}
    if architecture not in ARCHITECTURES or architecture == "UNKNOWN":
        return {
            "status": "ARCHITECTURE_NOT_VERIFIED",
            "profiles": [],
            "numeric_thresholds": None,
            "settings_auto_applied": False,
        }

    requirements: list[tuple[str, str, str]] = [
        (
            "load_actions", "INITIAL_DOCUMENT_NAVIGATION",
            "CHECK_DOCUMENT_LOAD_IF_INSTRUMENTED",
        ),
    ]
    # XHR/Fetch-triggered client-side routes require their own population
    # review only when both the soft route and async trigger are declared.
    if architecture in ("CSR_SPA", "HYDRATED", "MIXED"):
        if (result.get("soft_navigation_observed") is True
                and result.get("async_requests_observed") is True):
            requirements.append((
                "xhr_actions", "ASYNC_CLIENT_SIDE_ROUTE",
                "REVIEW_RUM_XHR_CAPTURE_AND_ACTION_COVERAGE",
            ))
        elif result.get("soft_navigation_observed") is True:
            requirements.append((
                "xhr_actions", "POSSIBLE_CLIENT_SIDE_ROUTE",
                "CONFIRM_XHR_FETCH_OR_CUSTOM_ACTION_BEFORE_KPM_SELECTION",
            ))
    if "custom_actions" in configured:
        requirements.append((
            "custom_actions", "OPERATOR_INSTRUMENTED_INTERACTION",
            "REVIEW_CUSTOM_ACTION_INSTRUMENTATION",
        ))
    profiles: list[dict[str, Any]] = []
    for category, use_case, review in requirements:
        current = configured.get(category)
        profiles.append({
            "action_type": category,
            "use_case": use_case,
            "review": review,
            "configuration_presence": (
                "KPM_DECLARED_IN_INPUT"
                if isinstance(current, str) and current in KPM_BY_ACTION[category]
                else "KPM_NOT_PROVIDED_NOT_PROOF_OF_DISABLED_CAPTURE"
            ),
            "configured_kpm": (
                current if isinstance(current, str)
                and current in KPM_BY_ACTION[category] else None
            ),
            "vendor_valid_kpm_options": sorted(KPM_BY_ACTION[category]),
            "prescribed_kpm": None,
            "prescribed_tolerated_seconds": None,
            "prescribed_frustrating_seconds": None,
        })
    return {
        "status": "CONTEXTUAL_KPM_OPTIONS_NOT_VERIFIED_RECOMMENDATION",
        "profiles": profiles,
        "numeric_thresholds": None,
        "settings_auto_applied": False,
    }

def explain_dynatrace_apdex_pt_br(result: Mapping[str, Any]) -> dict[str, Any]:
    """Produce a safe, readable advisory from a verdict, never from tenant data.

    This is *not* a RUM observation, HTML report projection or RASAi M25 KPM.
    """
    reasons = result.get("reasons", ())
    if not isinstance(reasons, (tuple, list)):
        reasons = ()
    formatted_reasons = []
    for reason in reasons:
        if not isinstance(reason, str):
            continue
        action, sep, code = reason.partition(":")
        label = _REASON_PT_BR.get(code if sep else action, "Condição sem descrição validada")
        prefix = {"load_actions": "Load", "xhr_actions": "XHR",
                  "custom_actions": "Custom", "capture": "Captura",
                  "action_counts": "População"}.get(action, "Evidência")
        formatted_reasons.append((prefix + ": " if sep else "") + label)
    supplied = result.get("observed_kpm", {})
    if not isinstance(supplied, Mapping):
        supplied = {}
    # A provenance label alone is not an authenticated HTTP observation:
    # the offline advisory can be invoked with arbitrary operator-supplied
    # metadata. Require the positive, internally set CLI read result and
    # exact read-scope contract before using the word "consultados".
    authenticated_settings = (
        result.get("settings_provenance") == "LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES"
        and result.get("input_source") == "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"
        and result.get("scope_provenance") == "AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS"
        and result.get("actual_dynatrace_tenant_consulted") is True
        and type(result.get("dynatrace_provider_requests")) is int
        and result["dynatrace_provider_requests"] == 1
    )
    return {
        "conclusao": _STATUS_PT_BR.get(
            result.get("status"), "Diagnóstico não determinável"
        ),
        "arquitetura_informada": (
            result.get("architecture")
            if result.get("architecture") in ARCHITECTURES else "UNKNOWN"
        ),
        "metricas_declaradas_na_configuracao": {
            label: str(supplied[key])
            for key, label in (
                ("load_actions", "Load"), ("xhr_actions", "XHR"),
                ("custom_actions", "Custom")
            )
            if isinstance(supplied.get(key), str)
            and supplied[key] in KPM_BY_ACTION[key]
        },
        "motivos": formatted_reasons,
        "proximos_passos": list(result.get("review_actions") or ()),
        "revisao_de_perfis_por_arquitetura": _architecture_action_review(result),
        "limite_metodologico": (
            ("Valores efetivos consultados no tenant via Settings API; "
             if authenticated_settings else
             "Configuração fornecida pelo operador, não verificada no tenant. ")
            + "A presença de configuração Load/XHR/Custom não comprova captura, "
            "população de ações, URL, período nem a mesma amostra da identificação de arquitetura. "
            "Os índices sintéticos de navegação e experiência do RASAi não foram recalculados. "
            "Não existem thresholds universais do Dynatrace por arquitetura."
        ),
    }

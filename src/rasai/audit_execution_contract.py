"""Canonical structured configuration contract for durable AUDIT execution jobs.

The HTTP/SaaS layer persists only non-secret audit choices. Provider credentials,
OIDC secrets and deployment credentials remain process/deployment environment
concerns and never enter an execution-job payload.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from rasai.content_context import (
    CONTENT_ORIGIN_ENV,
    CONTENT_RISK_PROFILE_ENV,
    EXPERIENCE_REQUIREMENT_ENV,
    FRESHNESS_SENSITIVITY_ENV,
    INTENDED_AUDIENCE_ENV,
    PAGE_PURPOSE_ENV,
    YMYL_CATEGORY_ENV,
    build_content_analysis_context,
)
from rasai.m21_web_performance import DEFAULT_CATEGORIES
from rasai.m23_cli import (
    DEFAULT_APDEX_CONCURRENCY,
    DEFAULT_APDEX_DELAY_SECONDS,
    DEFAULT_APDEX_MAX_PAGES,
    DEFAULT_APDEX_SAMPLES_PER_CONTEXT,
    MAX_APDEX_CONCURRENCY,
)
from rasai.m25_cli import (
    DEFAULT_UX_CONCURRENCY,
    DEFAULT_UX_DELAY_SECONDS,
    DEFAULT_UX_DEVICE_MIX,
    DEFAULT_UX_ERROR_SCOPE,
    DEFAULT_UX_KPM,
    DEFAULT_UX_MAX_PAGES,
    DEFAULT_UX_SAMPLES,
    DEFAULT_UX_SESSION_MODE,
    DEFAULT_UX_SETTLE_SECONDS,
    parse_device_mix,
)
from rasai.m25_dynatrace import SUPPORTED_TIME_KPMS
from rasai.provider_registry import cli_provider_choices, get_provider_registration
from rasai.provider_runtime_policy import AI_TIMEOUT_ENV, DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS

DEFAULT_WEB_PERFORMANCE_MAX_PAGES = 10
DEFAULT_LANGUAGE = "pt-BR"
DEFAULT_MARKET = "BR"
DEFAULT_MAX_PAGES = 100
DEFAULT_DEVICE_CONTEXT = "mobile"
DEFAULT_AI_PROVIDER = "none"
DEFAULT_AI_TIMEOUT_SECONDS = 180.0
DEFAULT_WEB_PERFORMANCE_FIELD_SOURCE = "auto"
DEFAULT_LIGHTHOUSE_CATEGORIES = ",".join(DEFAULT_CATEGORIES)

_CONTENT_PAYLOAD_TO_ENV = {
    "content_risk_profile": CONTENT_RISK_PROFILE_ENV,
    "ymyl_category": YMYL_CATEGORY_ENV,
    "page_purpose": PAGE_PURPOSE_ENV,
    "intended_audience": INTENDED_AUDIENCE_ENV,
    "experience_requirement": EXPERIENCE_REQUIREMENT_ENV,
    "freshness_sensitivity": FRESHNESS_SENSITIVITY_ENV,
    "content_origin": CONTENT_ORIGIN_ENV,
}

AUDIT_JOB_FIELDS = frozenset({
    "urls",
    "language", "market", "max_pages", "device_context",
    "ai_provider", "ai_model", "ai_reasoning", "ai_timeout_seconds",
    "ai_content_remediation", "ai_technical_remediation",
    "web_performance", "web_performance_max_pages", "web_performance_timeout_seconds",
    "web_performance_field_source", "lighthouse_categories",
    "synthetic_apdex", "apdex_threshold_seconds", "apdex_samples_per_context",
    "apdex_max_attempts_per_context", "apdex_max_pages", "apdex_timeout_seconds",
    "apdex_delay_seconds", "apdex_concurrency",
    "apdex_experience", "apdex_experience_samples", "apdex_experience_max_attempts",
    "apdex_experience_max_pages", "apdex_experience_device_mix",
    "apdex_experience_session_mode", "apdex_experience_kpm",
    "apdex_experience_satisfied_seconds", "apdex_experience_frustrated_seconds",
    "apdex_experience_errors", "apdex_experience_error_scope",
    "apdex_experience_settle_seconds", "apdex_experience_delay_seconds",
    "apdex_experience_concurrency",
    *_CONTENT_PAYLOAD_TO_ENV.keys(),
})


@dataclass(frozen=True, slots=True)
class AuditJobOption:
    name: str
    default: Any
    kind: str
    choices: tuple[str, ...] = ()
    required_when: str = ""
    description: str = ""


def audit_job_options() -> tuple[AuditJobOption, ...]:
    """Return the user-facing non-secret AUDIT configuration surface."""
    return (
        AuditJobOption("language", DEFAULT_LANGUAGE, "text", description="Idioma principal da análise."),
        AuditJobOption("market", DEFAULT_MARKET, "text", description="Mercado de referência."),
        AuditJobOption("max_pages", DEFAULT_MAX_PAGES, "integer", description="Máximo determinístico de páginas."),
        AuditJobOption("device_context", DEFAULT_DEVICE_CONTEXT, "enum", ("mobile", "desktop", "both")),
        AuditJobOption("ai_provider", DEFAULT_AI_PROVIDER, "enum", cli_provider_choices()),
        AuditJobOption("ai_model", "", "text", required_when="Somente quando houver override de modelo."),
        AuditJobOption("ai_reasoning", "", "text", required_when="Somente provider explícito que exponha reasoning configurável."),
        AuditJobOption("ai_timeout_seconds", DEFAULT_AI_TIMEOUT_SECONDS, "number"),
        AuditJobOption("ai_content_remediation", False, "boolean"),
        AuditJobOption("ai_technical_remediation", False, "boolean"),
        AuditJobOption("web_performance", False, "boolean"),
        AuditJobOption("web_performance_max_pages", DEFAULT_WEB_PERFORMANCE_MAX_PAGES, "integer"),
        AuditJobOption("web_performance_timeout_seconds", DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS, "number"),
        AuditJobOption("web_performance_field_source", DEFAULT_WEB_PERFORMANCE_FIELD_SOURCE, "enum", ("auto", "pagespeed", "crux", "none")),
        AuditJobOption("lighthouse_categories", DEFAULT_LIGHTHOUSE_CATEGORIES, "text"),
        AuditJobOption("synthetic_apdex", False, "boolean"),
        AuditJobOption("apdex_threshold_seconds", None, "number", required_when="Obrigatório quando Synthetic Navigation Apdex estiver habilitado."),
        AuditJobOption("apdex_samples_per_context", DEFAULT_APDEX_SAMPLES_PER_CONTEXT, "integer"),
        AuditJobOption("apdex_max_attempts_per_context", 125, "integer"),
        AuditJobOption("apdex_max_pages", DEFAULT_APDEX_MAX_PAGES, "integer"),
        AuditJobOption("apdex_timeout_seconds", None, "number", required_when="Quando omitido, o runtime usa max(45 s, 4T + 5 s)."),
        AuditJobOption("apdex_delay_seconds", DEFAULT_APDEX_DELAY_SECONDS, "number"),
        AuditJobOption("apdex_concurrency", DEFAULT_APDEX_CONCURRENCY, "integer"),
        AuditJobOption("apdex_experience", False, "boolean"),
        AuditJobOption("apdex_experience_samples", DEFAULT_UX_SAMPLES, "integer"),
        AuditJobOption("apdex_experience_max_attempts", 125, "integer"),
        AuditJobOption("apdex_experience_max_pages", DEFAULT_UX_MAX_PAGES, "integer"),
        AuditJobOption("apdex_experience_device_mix", DEFAULT_UX_DEVICE_MIX, "text", required_when="Percentuais Mobile/Desktop/Tablet devem totalizar 100%."),
        AuditJobOption("apdex_experience_session_mode", DEFAULT_UX_SESSION_MODE, "enum", ("cold", "warm")),
        AuditJobOption("apdex_experience_kpm", DEFAULT_UX_KPM, "enum", tuple(sorted(SUPPORTED_TIME_KPMS))),
        AuditJobOption("apdex_experience_satisfied_seconds", None, "number", required_when="Obrigatório no modo manual de Experience Apdex."),
        AuditJobOption("apdex_experience_frustrated_seconds", None, "number", required_when="Obrigatório no modo manual de Experience Apdex e deve ser maior que Satisfied."),
        AuditJobOption("apdex_experience_errors", True, "boolean"),
        AuditJobOption("apdex_experience_error_scope", DEFAULT_UX_ERROR_SCOPE, "enum", ("navigation", "first-party", "all")),
        AuditJobOption("apdex_experience_settle_seconds", DEFAULT_UX_SETTLE_SECONDS, "number"),
        AuditJobOption("apdex_experience_delay_seconds", DEFAULT_UX_DELAY_SECONDS, "number"),
        AuditJobOption("apdex_experience_concurrency", DEFAULT_UX_CONCURRENCY, "integer"),
        AuditJobOption("content_risk_profile", "auto", "enum", ("auto", "standard", "ymyl")),
        AuditJobOption("ymyl_category", "auto", "enum", ("auto", "none", "health-safety", "financial-security", "civic-societal", "other-significant-welfare")),
        AuditJobOption("page_purpose", "auto", "enum", ("auto", "informational", "transactional", "product-service", "review-comparison", "news-editorial", "support-documentation", "forum-ugc", "other")),
        AuditJobOption("intended_audience", "auto", "enum", ("auto", "general", "professional", "mixed")),
        AuditJobOption("experience_requirement", "auto", "enum", ("auto", "required", "beneficial", "not-expected")),
        AuditJobOption("freshness_sensitivity", "auto", "enum", ("auto", "low", "medium", "high")),
        AuditJobOption("content_origin", "auto", "enum", ("auto", "first-party", "third-party", "user-generated", "mixed")),
    )


def audit_job_defaults() -> dict[str, Any]:
    return {option.name: option.default for option in audit_job_options()}


def _bool(payload: Mapping[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"AUDIT payload field {name} must be boolean")
    return value


def _text(payload: Mapping[str, Any], name: str, default: str = "", *, choices: tuple[str, ...] = ()) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"AUDIT payload field {name} must be text")
    normalized = value.strip()
    if choices and normalized not in choices:
        raise ValueError(f"AUDIT payload field {name} must be one of: {', '.join(choices)}")
    return normalized


def _int(payload: Mapping[str, Any], name: str, default: int, *, minimum: int = 0, maximum: int = 1000000) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"AUDIT payload field {name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"AUDIT payload field {name} must be between {minimum} and {maximum}")
    return value


def _optional_positive_number(payload: Mapping[str, Any], name: str) -> float | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AUDIT payload field {name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"AUDIT payload field {name} must be a finite number > 0")
    return result


def _number(payload: Mapping[str, Any], name: str, default: float, *, minimum: float = 0.0) -> float:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AUDIT payload field {name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"AUDIT payload field {name} must be a finite number >= {minimum:g}")
    return result


def normalize_audit_job_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and materialize safe defaults for one durable AUDIT job."""
    unknown = sorted(set(payload) - AUDIT_JOB_FIELDS)
    if unknown:
        raise ValueError("unsupported AUDIT execution payload field(s): " + ", ".join(unknown))

    normalized = audit_job_defaults()
    normalized["language"] = _text(payload, "language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
    normalized["market"] = _text(payload, "market", DEFAULT_MARKET) or DEFAULT_MARKET
    normalized["max_pages"] = _int(payload, "max_pages", DEFAULT_MAX_PAGES, minimum=1, maximum=100000)
    normalized["device_context"] = _text(payload, "device_context", DEFAULT_DEVICE_CONTEXT, choices=("mobile", "desktop", "both"))
    normalized["ai_provider"] = _text(payload, "ai_provider", DEFAULT_AI_PROVIDER, choices=cli_provider_choices())
    normalized["ai_model"] = _text(payload, "ai_model", "")
    normalized["ai_reasoning"] = _text(payload, "ai_reasoning", "")
    normalized["ai_timeout_seconds"] = _number(payload, "ai_timeout_seconds", DEFAULT_AI_TIMEOUT_SECONDS, minimum=0.000001)
    normalized["ai_content_remediation"] = _bool(payload, "ai_content_remediation", False)
    normalized["ai_technical_remediation"] = _bool(payload, "ai_technical_remediation", False)

    if normalized["ai_provider"] == "auto" and normalized["ai_model"]:
        raise ValueError("AUDIT payload ai_model cannot be used with ai_provider=auto")
    if normalized["ai_reasoning"]:
        registration = get_provider_registration(normalized["ai_provider"])
        if registration is None or registration.reasoning_env is None:
            raise ValueError("AUDIT payload ai_reasoning requires an explicit provider with configurable reasoning")
        value = normalized["ai_reasoning"].upper()
        if value not in registration.reasoning_values:
            raise ValueError("AUDIT payload ai_reasoning is not supported by the selected provider")
        normalized["ai_reasoning"] = value

    normalized["web_performance"] = _bool(payload, "web_performance", False)
    normalized["web_performance_max_pages"] = _int(payload, "web_performance_max_pages", DEFAULT_WEB_PERFORMANCE_MAX_PAGES, minimum=0, maximum=100000)
    normalized["web_performance_timeout_seconds"] = _number(payload, "web_performance_timeout_seconds", DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS, minimum=0.000001)
    normalized["web_performance_field_source"] = _text(payload, "web_performance_field_source", DEFAULT_WEB_PERFORMANCE_FIELD_SOURCE, choices=("auto", "pagespeed", "crux", "none"))
    categories = _text(payload, "lighthouse_categories", DEFAULT_LIGHTHOUSE_CATEGORIES)
    parsed_categories = tuple(item.strip().casefold() for item in categories.split(",") if item.strip())
    if not parsed_categories or len(set(parsed_categories)) != len(parsed_categories) or any(item not in DEFAULT_CATEGORIES for item in parsed_categories):
        raise ValueError("AUDIT payload lighthouse_categories contains empty, duplicate or unsupported categories")
    normalized["lighthouse_categories"] = ",".join(parsed_categories)

    normalized["synthetic_apdex"] = _bool(payload, "synthetic_apdex", False)
    normalized["apdex_threshold_seconds"] = _optional_positive_number(payload, "apdex_threshold_seconds")
    normalized["apdex_samples_per_context"] = _int(payload, "apdex_samples_per_context", DEFAULT_APDEX_SAMPLES_PER_CONTEXT, minimum=1)
    normalized["apdex_max_attempts_per_context"] = _int(payload, "apdex_max_attempts_per_context", max(125, normalized["apdex_samples_per_context"]), minimum=1)
    if normalized["apdex_max_attempts_per_context"] < normalized["apdex_samples_per_context"]:
        raise ValueError("AUDIT payload apdex_max_attempts_per_context must be >= apdex_samples_per_context")
    normalized["apdex_max_pages"] = _int(payload, "apdex_max_pages", DEFAULT_APDEX_MAX_PAGES, minimum=0)
    normalized["apdex_timeout_seconds"] = _optional_positive_number(payload, "apdex_timeout_seconds")
    normalized["apdex_delay_seconds"] = _number(payload, "apdex_delay_seconds", DEFAULT_APDEX_DELAY_SECONDS, minimum=0)
    normalized["apdex_concurrency"] = _int(payload, "apdex_concurrency", DEFAULT_APDEX_CONCURRENCY, minimum=1, maximum=MAX_APDEX_CONCURRENCY)
    if normalized["synthetic_apdex"] and normalized["apdex_threshold_seconds"] is None:
        raise ValueError("AUDIT payload apdex_threshold_seconds is required when synthetic_apdex=true")
    if normalized["synthetic_apdex"] and normalized["apdex_timeout_seconds"] is not None and normalized["apdex_timeout_seconds"] <= 4.0 * normalized["apdex_threshold_seconds"]:
        raise ValueError("AUDIT payload apdex_timeout_seconds must be > 4T")

    normalized["apdex_experience"] = _bool(payload, "apdex_experience", False)
    normalized["apdex_experience_samples"] = _int(payload, "apdex_experience_samples", DEFAULT_UX_SAMPLES, minimum=1)
    normalized["apdex_experience_max_attempts"] = _int(payload, "apdex_experience_max_attempts", max(125, normalized["apdex_experience_samples"]), minimum=1)
    if normalized["apdex_experience_max_attempts"] < normalized["apdex_experience_samples"]:
        raise ValueError("AUDIT payload apdex_experience_max_attempts must be >= apdex_experience_samples")
    normalized["apdex_experience_max_pages"] = _int(payload, "apdex_experience_max_pages", DEFAULT_UX_MAX_PAGES, minimum=0)
    normalized["apdex_experience_device_mix"] = _text(payload, "apdex_experience_device_mix", DEFAULT_UX_DEVICE_MIX)
    parse_device_mix(normalized["apdex_experience_device_mix"])
    normalized["apdex_experience_session_mode"] = _text(payload, "apdex_experience_session_mode", DEFAULT_UX_SESSION_MODE, choices=("cold", "warm"))
    normalized["apdex_experience_kpm"] = _text(payload, "apdex_experience_kpm", DEFAULT_UX_KPM).upper()
    if normalized["apdex_experience_kpm"] not in SUPPORTED_TIME_KPMS:
        raise ValueError("AUDIT payload apdex_experience_kpm is not supported")
    normalized["apdex_experience_satisfied_seconds"] = _optional_positive_number(payload, "apdex_experience_satisfied_seconds")
    normalized["apdex_experience_frustrated_seconds"] = _optional_positive_number(payload, "apdex_experience_frustrated_seconds")
    normalized["apdex_experience_errors"] = _bool(payload, "apdex_experience_errors", True)
    normalized["apdex_experience_error_scope"] = _text(payload, "apdex_experience_error_scope", DEFAULT_UX_ERROR_SCOPE, choices=("navigation", "first-party", "all"))
    normalized["apdex_experience_settle_seconds"] = _number(payload, "apdex_experience_settle_seconds", DEFAULT_UX_SETTLE_SECONDS, minimum=0.000001)
    normalized["apdex_experience_delay_seconds"] = _number(payload, "apdex_experience_delay_seconds", DEFAULT_UX_DELAY_SECONDS, minimum=0)
    normalized["apdex_experience_concurrency"] = _int(payload, "apdex_experience_concurrency", DEFAULT_UX_CONCURRENCY, minimum=1, maximum=2)
    if normalized["apdex_experience"] and not normalized["synthetic_apdex"]:
        raise ValueError("AUDIT payload apdex_experience requires synthetic_apdex=true")
    if normalized["apdex_experience"]:
        satisfied = normalized["apdex_experience_satisfied_seconds"]
        frustrated = normalized["apdex_experience_frustrated_seconds"]
        if satisfied is None or frustrated is None:
            raise ValueError("AUDIT payload manual Experience Apdex requires satisfied and frustrated thresholds")
        if frustrated <= satisfied:
            raise ValueError("AUDIT payload apdex_experience_frustrated_seconds must be greater than satisfied")

    content_values = {
        name: _text(payload, name, "auto") or "auto"
        for name in _CONTENT_PAYLOAD_TO_ENV
    }
    build_content_analysis_context(
        risk_profile=content_values["content_risk_profile"],
        ymyl_category=content_values["ymyl_category"],
        page_purpose=content_values["page_purpose"],
        intended_audience=content_values["intended_audience"],
        experience_requirement=content_values["experience_requirement"],
        freshness_sensitivity=content_values["freshness_sensitivity"],
        content_origin=content_values["content_origin"],
    )
    normalized.update(content_values)

    urls = payload.get("urls")
    if urls is not None:
        if not isinstance(urls, list) or any(not isinstance(item, str) for item in urls):
            raise ValueError("AUDIT payload urls must be an array of strings")
        normalized["urls"] = list(urls)
    return normalized


def audit_job_environment_overrides(payload: Mapping[str, Any]) -> dict[str, str]:
    """Translate user-safe job options that are environment-only in the audit core."""
    normalized = normalize_audit_job_payload(payload)
    overrides = {
        AI_TIMEOUT_ENV: f"{normalized['ai_timeout_seconds']:g}",
        **{
            environment_name: str(normalized[payload_name])
            for payload_name, environment_name in _CONTENT_PAYLOAD_TO_ENV.items()
        },
    }
    if normalized["ai_reasoning"]:
        registration = get_provider_registration(normalized["ai_provider"])
        assert registration is not None and registration.reasoning_env is not None
        overrides[registration.reasoning_env] = normalized["ai_reasoning"]
    return overrides

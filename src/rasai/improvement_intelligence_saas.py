"""SaaS/control-plane contract for Improvement Intelligence.

Only feature-specific, non-secret execution choices enter durable jobs. AI provider,
model and reasoning belong to the canonical AUDIT AI fields and credentials remain in
the worker/integration secret boundary.
"""
from __future__ import annotations

from typing import Any, Mapping

from rasai.improvement_intelligence import (
    AI_ANALYSIS_LANGUAGE_ENV,
    DEFAULT_DOMAINS,
    DOMAINS_ENV,
    ENABLED_ENV,
    MAX_RECOMMENDATIONS_ENV,
    TIMEOUT_ENV,
    parse_domains,
    validate_analysis_language,
)

_INSTALLED = False
_FIELDS = frozenset(
    {
        "improvement_intelligence",
        "improvement_domains",
        "improvement_max_recommendations",
        "improvement_ai_timeout_seconds",
        "ai_analysis_language",
    }
)


def _bool(payload: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"AUDIT payload field {name} must be boolean")
    return value


def _text(payload: Mapping[str, Any], name: str, default: str = "") -> str:
    value = payload.get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"AUDIT payload field {name} must be text")
    return value.strip()


def _positive_int(payload: Mapping[str, Any], name: str, default: int, *, maximum: int) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"AUDIT payload field {name} must be an integer between 1 and {maximum}")
    return value


def _positive_number(payload: Mapping[str, Any], name: str, default: float) -> float:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise ValueError(f"AUDIT payload field {name} must be numeric and > 0")
    return float(value)


def _validate_extension(payload: Mapping[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    enabled = _bool(payload, "improvement_intelligence", False)
    language = validate_analysis_language(
        _text(payload, "ai_analysis_language", "auto") or "auto"
    )
    raw_domains = payload.get("improvement_domains", ",".join(DEFAULT_DOMAINS))
    if not isinstance(raw_domains, str):
        raise ValueError("AUDIT payload field improvement_domains must be comma-separated text")
    domains = parse_domains(raw_domains)
    maximum = _positive_int(payload, "improvement_max_recommendations", 30, maximum=100)
    timeout = _positive_number(payload, "improvement_ai_timeout_seconds", 240.0)

    if enabled:
        urls = normalized.get("urls")
        if not isinstance(urls, list) or len(urls) != 1 or not str(urls[0]).strip():
            raise ValueError(
                "Improvement Intelligence requires exactly one explicit URL in AUDIT payload urls"
            )
        selection = str(normalized.get("ai_provider") or "none").strip().casefold()
        if selection == "none":
            raise ValueError(
                "Improvement Intelligence requires the primary AUDIT ai_provider to be enabled"
            )

    normalized.update(
        {
            "improvement_intelligence": enabled,
            "improvement_domains": ",".join(domains),
            "improvement_max_recommendations": maximum,
            "improvement_ai_timeout_seconds": timeout,
            "ai_analysis_language": language,
        }
    )
    return normalized


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
    contract.AUDIT_JOB_FIELDS = frozenset((*base_fields, *_FIELDS))

    def options_with_improvement():
        values = list(original_options())
        known = {item.name for item in values}
        additions = (
            contract.AuditJobOption(
                "improvement_intelligence",
                False,
                "boolean",
                description=(
                    "Análise profunda evidence-bound; exige exatamente uma URL e usa a IA principal do AUDIT."
                ),
            ),
            contract.AuditJobOption(
                "improvement_domains",
                ",".join(DEFAULT_DOMAINS),
                "text",
                description="Domínios de análise separados por vírgula.",
            ),
            contract.AuditJobOption(
                "improvement_max_recommendations",
                30,
                "integer",
                description="Teto de recomendações estruturadas retornadas pela IA.",
            ),
            contract.AuditJobOption(
                "improvement_ai_timeout_seconds",
                240.0,
                "number",
                description="Timeout da chamada profunda; não cria seleção de provider paralela.",
            ),
            contract.AuditJobOption(
                "ai_analysis_language",
                "auto",
                "text",
                description="Idioma preferencial de leitura/resposta da IA; auto usa o idioma da auditoria.",
            ),
        )
        values.extend(item for item in additions if item.name not in known)
        return tuple(values)

    def defaults_with_improvement() -> dict[str, Any]:
        values = dict(original_defaults())
        values.update(
            {
                "improvement_intelligence": False,
                "improvement_domains": ",".join(DEFAULT_DOMAINS),
                "improvement_max_recommendations": 30,
                "improvement_ai_timeout_seconds": 240.0,
                "ai_analysis_language": "auto",
            }
        )
        return values

    def normalize_with_improvement(payload: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(payload) - contract.AUDIT_JOB_FIELDS)
        if unknown:
            raise ValueError("unsupported AUDIT execution payload field(s): " + ", ".join(unknown))
        base_payload = {key: value for key, value in payload.items() if key not in _FIELDS}
        normalized = dict(original_normalize(base_payload))
        return _validate_extension(payload, normalized)

    def environment_with_improvement(payload: Mapping[str, Any]) -> dict[str, str]:
        base_payload = {key: value for key, value in payload.items() if key not in _FIELDS}
        overrides = dict(original_environment(base_payload))
        normalized = normalize_with_improvement(payload)
        overrides.update(
            {
                ENABLED_ENV: "true" if normalized["improvement_intelligence"] else "false",
                DOMAINS_ENV: str(normalized["improvement_domains"]),
                MAX_RECOMMENDATIONS_ENV: str(normalized["improvement_max_recommendations"]),
                TIMEOUT_ENV: f"{float(normalized['improvement_ai_timeout_seconds']):g}",
                AI_ANALYSIS_LANGUAGE_ENV: str(normalized["ai_analysis_language"]),
            }
        )
        return overrides

    contract.audit_job_options = options_with_improvement
    contract.audit_job_defaults = defaults_with_improvement
    contract.normalize_audit_job_payload = normalize_with_improvement
    contract.audit_job_environment_overrides = environment_with_improvement
    contract._rasai_improvement_intelligence_saas = True

    try:
        from rasai import execution_contract

        if getattr(execution_contract, "normalize_audit_job_payload", None) is original_normalize:
            execution_contract.normalize_audit_job_payload = normalize_with_improvement
    except Exception:
        pass
    try:
        from rasai import worker

        if getattr(worker, "normalize_audit_job_payload", None) is original_normalize:
            worker.normalize_audit_job_payload = normalize_with_improvement
        if getattr(worker, "audit_job_environment_overrides", None) is original_environment:
            worker.audit_job_environment_overrides = environment_with_improvement
    except Exception:
        pass
    try:
        from rasai.web import saas_management_routes

        if getattr(saas_management_routes, "audit_job_options", None) is original_options:
            saas_management_routes.audit_job_options = options_with_improvement
    except Exception:
        pass

    _INSTALLED = True

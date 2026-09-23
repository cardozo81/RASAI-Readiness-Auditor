"""SaaS/control-plane contract for CAT-10 passive security.

Only non-secret feature choices enter durable AUDIT jobs. OSV/CISA KEV require no
credential here. Optional AI reuses the canonical Improvement Intelligence provider
and contract restricted to SECURITY when CAT-08 is not otherwise requested.
"""
from __future__ import annotations

from typing import Any, Mapping

from rasai.passive_security import (
    COOKIES_ENV,
    ENABLED_ENV,
    EXTERNAL_TIMEOUT_ENV,
    HEADERS_ENV,
    KEV_ENV,
    OSV_ENV,
    RESOURCES_ENV,
    RUNTIME_ENV,
    THIRD_PARTY_ENV,
)
from rasai.improvement_intelligence import (
    DOMAINS_ENV as IMPROVEMENT_DOMAINS_ENV,
    ENABLED_ENV as IMPROVEMENT_ENABLED_ENV,
    parse_domains,
)

_INSTALLED = False
_FIELDS = frozenset({
    "passive_security",
    "security_headers",
    "security_cookies",
    "security_resources",
    "security_third_party",
    "security_runtime_correlation",
    "security_osv",
    "security_cisa_kev",
    "security_external_timeout_seconds",
    "passive_security_ai",
})


def _bool(payload: Mapping[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"AUDIT payload field {name} must be boolean")
    return value


def _timeout(payload: Mapping[str, Any]) -> float:
    value = payload.get("security_external_timeout_seconds", 15.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("AUDIT payload field security_external_timeout_seconds must be numeric")
    result = float(value)
    if result <= 0 or result > 300:
        raise ValueError("AUDIT payload field security_external_timeout_seconds must be >0 and <=300")
    return result


def _validate_extension(payload: Mapping[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    enabled = _bool(payload, "passive_security", False)
    ai = _bool(payload, "passive_security_ai", False)
    if ai and not enabled:
        raise ValueError("passive_security_ai requires passive_security=true")
    if ai:
        urls = normalized.get("urls")
        if not isinstance(urls, list) or len(urls) != 1 or not str(urls[0]).strip():
            raise ValueError("passive_security_ai requires exactly one explicit URL")
        # Optional advisory AI may be requested even when the provider is currently
        # unavailable; deterministic passive-security analysis must still execute.
    normalized.update({
        "passive_security": enabled,
        "security_headers": _bool(payload, "security_headers", True),
        "security_cookies": _bool(payload, "security_cookies", True),
        "security_resources": _bool(payload, "security_resources", True),
        "security_third_party": _bool(payload, "security_third_party", True),
        "security_runtime_correlation": _bool(payload, "security_runtime_correlation", True),
        "security_osv": _bool(payload, "security_osv", True),
        "security_cisa_kev": _bool(payload, "security_cisa_kev", True),
        "security_external_timeout_seconds": _timeout(payload),
        "passive_security_ai": ai,
    })
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

    def options_with_security():
        values = list(original_options())
        known = {item.name for item in values}
        additions = (
            contract.AuditJobOption("passive_security", False, "boolean", description="CAT-10 Segurança Passiva; sem active scanning."),
            contract.AuditJobOption("security_headers", True, "boolean", description="HTTPS/redirects, headers, CSP, CORS e políticas cross-origin."),
            contract.AuditJobOption("security_cookies", True, "boolean", description="Atributos de Set-Cookie com redaction de valores."),
            contract.AuditJobOption("security_resources", True, "boolean", description="Scripts, recursos, mixed content, forms e iframes persistidos."),
            contract.AuditJobOption("security_third_party", True, "boolean", description="Classificação first-party/third-party e exposição externa."),
            contract.AuditJobOption("security_runtime_correlation", True, "boolean", description="Reutiliza requestfailed/HTTP/console/page errors; não altera Apdex."),
            contract.AuditJobOption("security_osv", True, "boolean", description="OSV somente com componente+versão identificados com confiança suficiente."),
            contract.AuditJobOption("security_cisa_kev", True, "boolean", description="Correlação CVE com CISA KEV."),
            contract.AuditJobOption("security_external_timeout_seconds", 15.0, "number", description="Timeout por integração externa de vulnerability intelligence."),
            contract.AuditJobOption("passive_security_ai", False, "boolean", description="Enriquecimento advisory pela IA principal, restrito ao domínio SECURITY."),
        )
        values.extend(item for item in additions if item.name not in known)
        return tuple(values)

    def defaults_with_security() -> dict[str, Any]:
        values = dict(original_defaults())
        values.update({
            "passive_security": False,
            "security_headers": True,
            "security_cookies": True,
            "security_resources": True,
            "security_third_party": True,
            "security_runtime_correlation": True,
            "security_osv": True,
            "security_cisa_kev": True,
            "security_external_timeout_seconds": 15.0,
            "passive_security_ai": False,
        })
        return values

    def normalize_with_security(payload: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(payload) - contract.AUDIT_JOB_FIELDS)
        if unknown:
            raise ValueError("unsupported AUDIT execution payload field(s): " + ", ".join(unknown))
        base_payload = {key: value for key, value in payload.items() if key not in _FIELDS}
        normalized = dict(original_normalize(base_payload))
        return _validate_extension(payload, normalized)

    def environment_with_security(payload: Mapping[str, Any]) -> dict[str, str]:
        base_payload = {key: value for key, value in payload.items() if key not in _FIELDS}
        overrides = dict(original_environment(base_payload))
        normalized = normalize_with_security(payload)
        overrides.update({
            ENABLED_ENV: "true" if normalized["passive_security"] else "false",
            HEADERS_ENV: "true" if normalized["security_headers"] else "false",
            COOKIES_ENV: "true" if normalized["security_cookies"] else "false",
            RESOURCES_ENV: "true" if normalized["security_resources"] else "false",
            THIRD_PARTY_ENV: "true" if normalized["security_third_party"] else "false",
            RUNTIME_ENV: "true" if normalized["security_runtime_correlation"] else "false",
            OSV_ENV: "true" if normalized["security_osv"] else "false",
            KEV_ENV: "true" if normalized["security_cisa_kev"] else "false",
            EXTERNAL_TIMEOUT_ENV: f"{float(normalized['security_external_timeout_seconds']):g}",
        })
        if normalized["passive_security_ai"]:
            # Preserve CAT-08 only when it was explicitly enabled in the base payload.
            # Otherwise CAT-10 reuses the same engine strictly for SECURITY.
            current_enabled = str(overrides.get(IMPROVEMENT_ENABLED_ENV) or "").casefold() == "true"
            if current_enabled:
                raw_domains = overrides.get(IMPROVEMENT_DOMAINS_ENV, "")
                domains = list(parse_domains(raw_domains)) if raw_domains else []
                if "SECURITY" not in domains:
                    domains.append("SECURITY")
            else:
                domains = ["SECURITY"]
            overrides[IMPROVEMENT_ENABLED_ENV] = "true"
            overrides[IMPROVEMENT_DOMAINS_ENV] = ",".join(domains)
        return overrides

    contract.audit_job_options = options_with_security
    contract.audit_job_defaults = defaults_with_security
    contract.normalize_audit_job_payload = normalize_with_security
    contract.audit_job_environment_overrides = environment_with_security
    contract._rasai_passive_security_saas = True

    try:
        from rasai import execution_contract
        if getattr(execution_contract, "normalize_audit_job_payload", None) is original_normalize:
            execution_contract.normalize_audit_job_payload = normalize_with_security
    except Exception:
        pass
    try:
        from rasai import worker
        if getattr(worker, "normalize_audit_job_payload", None) is original_normalize:
            worker.normalize_audit_job_payload = normalize_with_security
        if getattr(worker, "audit_job_environment_overrides", None) is original_environment:
            worker.audit_job_environment_overrides = environment_with_security
    except Exception:
        pass
    try:
        from rasai.web import saas_management_routes
        if getattr(saas_management_routes, "audit_job_options", None) is original_options:
            saas_management_routes.audit_job_options = options_with_security
    except Exception:
        pass
    _INSTALLED = True


__all__ = ["install"]

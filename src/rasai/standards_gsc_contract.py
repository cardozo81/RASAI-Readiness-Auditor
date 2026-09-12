"""Non-secret Google Search Console property context for local and SaaS execution."""
from __future__ import annotations

import sys
from typing import Any, Mapping
from urllib.parse import urlparse

from rasai.standards_service_registry import GSC_SITE_URL_ENV
from rasai.standards_runtime import install_service_contract

_FIELD = "gsc_site_url"


def _validate_site_url(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("AUDIT payload field gsc_site_url must be text")
    text = value.strip()
    if not text:
        return ""
    if text.startswith("sc-domain:"):
        domain = text.removeprefix("sc-domain:").strip().strip(".")
        if not domain or "/" in domain or "://" in domain:
            raise ValueError("gsc_site_url sc-domain property is invalid")
        return f"sc-domain:{domain}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("gsc_site_url must be an absolute http(s) URL or sc-domain:<domain>")
    return text


def _rebind(contract: Any) -> None:
    assignments = {
        "rasai.execution_contract": {"normalize_audit_job_payload": contract.normalize_audit_job_payload},
        "rasai.worker": {
            "normalize_audit_job_payload": contract.normalize_audit_job_payload,
            "audit_job_environment_overrides": contract.audit_job_environment_overrides,
        },
        "rasai.saas_context_integration": {"normalize_audit_job_payload": contract.normalize_audit_job_payload},
        "rasai.web.saas_management_routes": {"audit_job_options": contract.audit_job_options},
    }
    for module_name, values in assignments.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name, value in values.items():
            setattr(module, name, value)


def install() -> None:
    install_service_contract()
    from rasai import audit_execution_contract as contract

    if getattr(contract, "_rasai_gsc_property_contract", False):
        _rebind(contract)
        return

    original_fields = contract.AUDIT_JOB_FIELDS
    original_options = contract.audit_job_options
    original_defaults = contract.audit_job_defaults
    original_normalize = contract.normalize_audit_job_payload
    original_environment = contract.audit_job_environment_overrides
    contract.AUDIT_JOB_FIELDS = frozenset((*original_fields, _FIELD))

    def options_with_gsc_property():
        options = list(original_options())
        if not any(item.name == _FIELD for item in options):
            options.append(contract.AuditJobOption(
                _FIELD,
                "",
                "text",
                required_when="Obrigatório quando Google Search Console estiver habilitado.",
                description="Search Console property/siteUrl; aceita URL-prefix ou sc-domain:<domínio>.",
            ))
        return tuple(options)

    def defaults_with_gsc_property():
        result = dict(original_defaults())
        result[_FIELD] = ""
        return result

    def normalize_with_gsc_property(payload: Mapping[str, Any]):
        raw = dict(payload)
        site_url = _validate_site_url(raw.pop(_FIELD, ""))
        normalized = dict(original_normalize(raw))
        normalized[_FIELD] = site_url
        return normalized

    def environment_with_gsc_property(payload: Mapping[str, Any]):
        raw = dict(payload)
        site_url = _validate_site_url(raw.pop(_FIELD, ""))
        overrides = dict(original_environment(raw))
        if site_url:
            overrides[GSC_SITE_URL_ENV] = site_url
        return overrides

    contract.audit_job_options = options_with_gsc_property
    contract.audit_job_defaults = defaults_with_gsc_property
    contract.normalize_audit_job_payload = normalize_with_gsc_property
    contract.audit_job_environment_overrides = environment_with_gsc_property
    contract._rasai_gsc_property_contract = True
    _rebind(contract)

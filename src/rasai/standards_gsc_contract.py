"""Non-secret Google Search Console context for local and SaaS execution."""
from __future__ import annotations

import sys
from typing import Any, Mapping
from urllib.parse import urlparse

from rasai.standards_gsc_policy import (
    DEFAULT_GSC_FINAL_DATA_LAG_DAYS,
    DEFAULT_GSC_SEARCH_ANALYTICS_DAYS,
    DEFAULT_GSC_SEARCH_MAX_ROWS,
    GSC_FINAL_DATA_LAG_DAYS_ENV,
    GSC_SEARCH_ANALYTICS_DAYS_ENV,
    GSC_SEARCH_MAX_ROWS_ENV,
    final_data_lag_days,
    search_analytics_days,
    search_max_rows,
)
from rasai.standards_service_registry import GSC_SITE_URL_ENV
from rasai.standards_runtime import install_service_contract

_SITE_FIELD = "gsc_site_url"
_DAYS_FIELD = "gsc_search_analytics_days"
_MAX_ROWS_FIELD = "gsc_search_max_rows"
_LAG_FIELD = "gsc_final_data_lag_days"
_FIELDS = frozenset({_SITE_FIELD, _DAYS_FIELD, _MAX_ROWS_FIELD, _LAG_FIELD})


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
    contract.AUDIT_JOB_FIELDS = frozenset((*original_fields, *_FIELDS))

    def options_with_gsc_context():
        options = list(original_options())
        existing = {item.name for item in options}
        additions = (
            contract.AuditJobOption(
                _SITE_FIELD,
                "",
                "text",
                required_when="Obrigatório quando Google Search Console estiver explicitamente habilitado.",
                description="Search Console property/siteUrl; aceita URL-prefix ou sc-domain:<domínio>.",
            ),
            contract.AuditJobOption(
                _DAYS_FIELD,
                DEFAULT_GSC_SEARCH_ANALYTICS_DAYS,
                "integer",
                description="Quantidade de dias finalizados de Search Analytics coletados automaticamente; 0 desliga apenas essa subcoleta.",
            ),
            contract.AuditJobOption(
                _MAX_ROWS_FIELD,
                DEFAULT_GSC_SEARCH_MAX_ROWS,
                "integer",
                description="Teto de linhas de Search Analytics por auditoria.",
            ),
            contract.AuditJobOption(
                _LAG_FIELD,
                DEFAULT_GSC_FINAL_DATA_LAG_DAYS,
                "integer",
                description="Defasagem em dias usada para preferir dados Search Analytics finalizados.",
            ),
        )
        options.extend(item for item in additions if item.name not in existing)
        return tuple(options)

    def defaults_with_gsc_context():
        result = dict(original_defaults())
        result[_SITE_FIELD] = ""
        result[_DAYS_FIELD] = DEFAULT_GSC_SEARCH_ANALYTICS_DAYS
        result[_MAX_ROWS_FIELD] = DEFAULT_GSC_SEARCH_MAX_ROWS
        result[_LAG_FIELD] = DEFAULT_GSC_FINAL_DATA_LAG_DAYS
        return result

    def normalize_with_gsc_context(payload: Mapping[str, Any]):
        raw = dict(payload)
        site_url = _validate_site_url(raw.pop(_SITE_FIELD, ""))
        days = search_analytics_days(raw.pop(_DAYS_FIELD, None))
        max_rows = search_max_rows(raw.pop(_MAX_ROWS_FIELD, None))
        lag_days = final_data_lag_days(raw.pop(_LAG_FIELD, None))
        explicitly_enabled = raw.get("gsc_enabled") is True
        if explicitly_enabled and not site_url:
            raise ValueError("AUDIT payload gsc_enabled=true requires gsc_site_url")
        normalized = dict(original_normalize(raw))
        normalized[_SITE_FIELD] = site_url
        normalized[_DAYS_FIELD] = days
        normalized[_MAX_ROWS_FIELD] = max_rows
        normalized[_LAG_FIELD] = lag_days
        return normalized

    def environment_with_gsc_context(payload: Mapping[str, Any]):
        normalized = normalize_with_gsc_context(payload)
        raw = {key: value for key, value in payload.items() if key not in _FIELDS}
        overrides = dict(original_environment(raw))
        site_url = normalized[_SITE_FIELD]
        if site_url:
            overrides[GSC_SITE_URL_ENV] = site_url
        overrides[GSC_SEARCH_ANALYTICS_DAYS_ENV] = str(normalized[_DAYS_FIELD])
        overrides[GSC_SEARCH_MAX_ROWS_ENV] = str(normalized[_MAX_ROWS_FIELD])
        overrides[GSC_FINAL_DATA_LAG_DAYS_ENV] = str(normalized[_LAG_FIELD])
        return overrides

    contract.audit_job_options = options_with_gsc_context
    contract.audit_job_defaults = defaults_with_gsc_context
    contract.normalize_audit_job_payload = normalize_with_gsc_context
    contract.audit_job_environment_overrides = environment_with_gsc_context
    contract._rasai_gsc_property_contract = True
    _rebind(contract)

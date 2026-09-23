"""SaaS reconciliation for credential-driven standards services.

Durable payloads preserve explicit choices only. Omitted/null PageSpeed and CrUX
controls delegate to worker requirements. Search Console additionally requires
job-scoped property context so one tenant cannot inherit another property's context.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from rasai.standards_gsc_contract import install as install_gsc_contract
from rasai.standards_service_registry import GSC_ENABLED_ENV, GSC_SITE_URL_ENV, service, service_state

_CREDENTIAL_FIELDS = {
    "pagespeed_enabled": "RASAI_PAGESPEED_ENABLED",
    "crux_enabled": "RASAI_CRUX_ENABLED",
    "gsc_enabled": GSC_ENABLED_ENV,
}


def _requirements_ready(service_id: str) -> bool:
    item = service(service_id)
    required_names = (*item.credential_envs, *item.config_envs)
    return all((os.environ.get(name) or "").strip() for name in required_names)


def _explicit(payload: Mapping[str, Any], field: str) -> bool:
    return field in payload and payload[field] is not None


def _requested(payload: Mapping[str, Any], field: str, service_id: str) -> bool:
    if _explicit(payload, field):
        return bool(payload[field]) and _requirements_ready(service_id)
    return bool(service_state(service(service_id))["effective_enabled"])


def install() -> None:
    install_gsc_contract()
    from rasai import audit_execution_contract as contract
    from rasai import worker

    if getattr(worker, "_rasai_standards_saas_reconciliation", False):
        return

    original_environment = contract.audit_job_environment_overrides

    def environment_overrides(payload: Mapping[str, Any]) -> dict[str, str]:
        overrides = dict(original_environment(payload))
        # PageSpeed/CrUX may inherit worker-level credentials when the job is in auto
        # mode. Their keys do not embed tenant/property context.
        for field in ("pagespeed_enabled", "crux_enabled"):
            if not _explicit(payload, field):
                overrides.pop(_CREDENTIAL_FIELDS[field], None)

        # Search Console is property scoped. The property must always come from this
        # durable job. An empty override deliberately masks any process-global property
        # so explicit/auto GSC cannot inherit another tenant's context.
        job_site_url = str(payload.get("gsc_site_url") or "").strip()
        if job_site_url:
            overrides[GSC_SITE_URL_ENV] = job_site_url
        else:
            overrides[GSC_SITE_URL_ENV] = ""

        if not _explicit(payload, "gsc_enabled") and job_site_url:
            overrides.pop(GSC_ENABLED_ENV, None)
        elif not _explicit(payload, "gsc_enabled"):
            overrides[GSC_ENABLED_ENV] = "false"
        return overrides

    contract.audit_job_environment_overrides = environment_overrides
    worker.audit_job_environment_overrides = environment_overrides

    original_arguments = worker._audit_arguments

    def audit_arguments(store: Any, job: Any, audits_root: Any) -> list[str]:
        argv = list(original_arguments(store, job, audits_root))
        payload = job.payload
        # The aggregate web-performance switch is a current hard-off when explicitly
        # present in the job. Otherwise individual PageSpeed/CrUX readiness may activate
        # the aggregate runtime needed by M21.
        if "web_performance" in payload:
            return argv
        should_enable = (
            _requested(payload, "pagespeed_enabled", "pagespeed")
            or _requested(payload, "crux_enabled", "crux")
        )
        if should_enable and "--no-web-performance" in argv:
            index = argv.index("--no-web-performance")
            argv[index] = "--web-performance"
        return argv

    worker._audit_arguments = audit_arguments
    worker._rasai_standards_saas_reconciliation = True

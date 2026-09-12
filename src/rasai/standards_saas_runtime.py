"""SaaS reconciliation for credential-driven standards services.

Durable payloads preserve explicit choices only. Omitting PageSpeed/CrUX delegates to
the worker credential-driven default. Search Console additionally requires job-scoped
property context so one tenant cannot inherit another property's configuration.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from rasai.standards_gsc_contract import install as install_gsc_contract
from rasai.standards_service_registry import GSC_ENABLED_ENV, service, service_state

_CREDENTIAL_FIELDS = {
    "pagespeed_enabled": "RASAI_PAGESPEED_ENABLED",
    "crux_enabled": "RASAI_CRUX_ENABLED",
    "gsc_enabled": GSC_ENABLED_ENV,
}


def _requirements_ready(service_id: str) -> bool:
    item = service(service_id)
    required_names = (*item.credential_envs, *item.config_envs)
    return all((os.environ.get(name) or "").strip() for name in required_names)


def _requested(payload: Mapping[str, Any], field: str, service_id: str) -> bool:
    if field in payload:
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
        # PageSpeed/CrUX may safely inherit a worker-level secret when the job omitted
        # the corresponding toggle. No target/property context is embedded in the key.
        for field in ("pagespeed_enabled", "crux_enabled"):
            if field not in payload:
                overrides.pop(_CREDENTIAL_FIELDS[field], None)

        # Search Console is tenant/property scoped. Credential-driven enablement is
        # allowed only when this durable job carries its own non-secret property.
        if "gsc_enabled" not in payload and str(payload.get("gsc_site_url") or "").strip():
            overrides.pop(GSC_ENABLED_ENV, None)
        elif "gsc_enabled" not in payload:
            overrides[GSC_ENABLED_ENV] = "false"
        return overrides

    contract.audit_job_environment_overrides = environment_overrides
    worker.audit_job_environment_overrides = environment_overrides

    original_arguments = worker._audit_arguments

    def audit_arguments(store: Any, job: Any, audits_root: Any) -> list[str]:
        argv = list(original_arguments(store, job, audits_root))
        payload = job.payload
        # The aggregate web-performance switch is part of the current prepublication
        # contract. When explicitly present it remains authoritative for that job;
        # otherwise PageSpeed/CrUX service readiness can activate the aggregate runtime.
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

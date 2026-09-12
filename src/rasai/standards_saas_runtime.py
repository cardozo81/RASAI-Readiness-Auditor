"""SaaS reconciliation for credential-driven standards services.

Durable payloads preserve explicit choices only. Omitting PageSpeed/CrUX/GSC delegates
to the worker credential-driven default; false is an explicit disable; true is an
explicit request that still requires the worker credential and mandatory context.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from rasai.standards_gsc_contract import install as install_gsc_contract
from rasai.standards_service_registry import service, service_state

_CREDENTIAL_FIELDS = {
    "pagespeed_enabled": "RASAI_PAGESPEED_ENABLED",
    "crux_enabled": "RASAI_CRUX_ENABLED",
    "gsc_enabled": "RASAI_GSC_ENABLED",
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
        # Omitted credential-driven fields must not be materialized as false. This lets
        # each worker resolve readiness from its own secret/configuration environment.
        for field, env_name in _CREDENTIAL_FIELDS.items():
            if field not in payload:
                overrides.pop(env_name, None)
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

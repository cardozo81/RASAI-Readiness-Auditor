"""SaaS/worker projection of the canonical capture-context contract."""
from __future__ import annotations

from typing import Any

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION


_INSTALLED = False


def install() -> None:
    """Annotate successful AUDIT worker results with effective context metadata."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import worker
    from rasai.audit_execution_contract import normalize_audit_job_payload

    if getattr(worker, "_rasai_context_scope_worker", False):
        _INSTALLED = True
        return

    original = worker._run_audit

    def run_audit_with_context(store: Any, job: Any, audits_root: Any):
        result = original(store, job, audits_root)
        normalized = normalize_audit_job_payload(job.payload)
        metadata = dict(result.metadata)
        metadata.update(
            {
                "context_scope_contract": CONTEXT_SCOPE_CONTRACT_VERSION,
                "device_context": normalized["device_context"],
                "origin_resources_reused_across_devices": True,
            }
        )
        return worker.WorkerResult(result_ref=result.result_ref, metadata=metadata)

    worker._run_audit = run_audit_with_context
    worker._rasai_context_scope_worker = True
    _INSTALLED = True

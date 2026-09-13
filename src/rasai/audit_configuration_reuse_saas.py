"""SaaS/control-plane adapter for completed-AUD configuration reuse."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rasai.audit_configuration_reuse import (
    KIND_AUDIT_PAYLOAD,
    PROVENANCE_FIELDS,
    changed_fields,
    load_reusable_audit_configuration,
    strip_provenance,
)
from rasai.audit_configuration_reuse_runtime import configuration_context

_INSTALLED = False


def _validate_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    source = payload.get("configuration_source_audit_id")
    if source not in (None, ""):
        if not isinstance(source, str) or not source.strip().upper().startswith("AUD-"):
            raise ValueError("configuration_source_audit_id must be an AUD-* identifier")
        result["configuration_source_audit_id"] = source.strip().upper()
    source_hash = payload.get("configuration_source_hash")
    if source_hash not in (None, ""):
        if not isinstance(source_hash, str) or len(source_hash.strip()) != 64:
            raise ValueError("configuration_source_hash must be a SHA-256 hex digest")
        try:
            int(source_hash.strip(), 16)
        except ValueError as exc:
            raise ValueError("configuration_source_hash must be a SHA-256 hex digest") from exc
        result["configuration_source_hash"] = source_hash.strip().lower()
    series = payload.get("execution_series_id")
    if series not in (None, ""):
        if not isinstance(series, str) or not series.strip().startswith("SER-"):
            raise ValueError("execution_series_id must be a SER-* identifier")
        result["execution_series_id"] = series.strip()
    changed = payload.get("configuration_changed_fields")
    if changed not in (None, ""):
        if not isinstance(changed, (list, tuple)) or any(not isinstance(item, str) for item in changed):
            raise ValueError("configuration_changed_fields must be a list of field names")
        result["configuration_changed_fields"] = list(changed)
    return result


def install() -> None:
    """Extend AUDIT payload validation and bind provenance before worker execution."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_execution_contract as contract
    from rasai import cost_forecast, execution_contract, worker

    original_normalize = contract.normalize_audit_job_payload
    original_environment = contract.audit_job_environment_overrides

    def normalize_with_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = original_normalize(strip_provenance(payload))
        normalized.update(_validate_provenance(payload))
        return normalized

    def environment_without_provenance(payload: Mapping[str, Any]) -> dict[str, str]:
        return original_environment(strip_provenance(payload))

    contract.normalize_audit_job_payload = normalize_with_provenance
    contract.audit_job_environment_overrides = environment_without_provenance
    contract.AUDIT_JOB_FIELDS = frozenset(set(contract.AUDIT_JOB_FIELDS) | set(PROVENANCE_FIELDS))

    # These modules import the contract callable directly at module import time.
    execution_contract.normalize_audit_job_payload = normalize_with_provenance
    worker.normalize_audit_job_payload = normalize_with_provenance
    worker.audit_job_environment_overrides = environment_without_provenance
    if hasattr(cost_forecast, "normalize_audit_job_payload"):
        cost_forecast.normalize_audit_job_payload = normalize_with_provenance

    if not getattr(worker, "_rasai_audit_configuration_reuse", False):
        original_run_audit = worker._run_audit

        def run_audit_with_configuration(store: Any, job: Any, audits_root: Any):
            normalized = normalize_with_provenance(job.payload)
            effective = strip_provenance(normalized)
            with configuration_context(
                kind=KIND_AUDIT_PAYLOAD,
                configuration=effective,
                source_audit_id=(
                    str(normalized["configuration_source_audit_id"])
                    if normalized.get("configuration_source_audit_id")
                    else None
                ),
                source_configuration_hash=(
                    str(normalized["configuration_source_hash"])
                    if normalized.get("configuration_source_hash")
                    else None
                ),
                changed_fields=tuple(
                    str(item) for item in normalized.get("configuration_changed_fields", ())
                ),
                execution_series_id=(
                    str(normalized["execution_series_id"])
                    if normalized.get("execution_series_id")
                    else None
                ),
                scope={
                    "surface": "saas",
                    "project_id": job.project_id,
                    "property_id": job.property_id,
                    "environment_id": job.environment_id,
                    "job_id": job.job_id,
                },
            ):
                return original_run_audit(store, job, audits_root)

        worker._run_audit = run_audit_with_configuration
        worker._rasai_audit_configuration_reuse = True

    _INSTALLED = True


def build_reused_payload(
    audits_root: str | Path,
    source_audit_id: str,
    overrides: Mapping[str, Any] | None,
    *,
    project_id: str,
    property_id: str,
    environment_id: str,
) -> dict[str, Any]:
    """Resolve one completed source AUD into a new durable AUDIT payload."""
    install()
    source = load_reusable_audit_configuration(
        audits_root,
        source_audit_id,
        expected_kind=KIND_AUDIT_PAYLOAD,
    )
    expected_scope = {
        "project_id": project_id,
        "property_id": property_id,
        "environment_id": environment_id,
    }
    for name, value in expected_scope.items():
        persisted = source.scope.get(name)
        if persisted and persisted != value:
            raise ValueError(
                f"{source.audit_id} pertence a outro {name}; reuso SaaS exige o mesmo escopo de execução"
            )

    from rasai import audit_execution_contract as contract

    base = strip_provenance(source.configuration)
    requested = dict(overrides or {})
    forbidden = sorted(set(requested) & set(PROVENANCE_FIELDS))
    if forbidden:
        raise ValueError("provenance fields are server-managed: " + ", ".join(forbidden))
    merged = dict(base)
    merged.update(requested)
    effective = strip_provenance(contract.normalize_audit_job_payload(merged))
    differences = changed_fields(base, effective)
    effective.update(
        {
            "configuration_source_audit_id": source.audit_id,
            "configuration_source_hash": source.configuration_hash,
            "configuration_changed_fields": list(differences),
            "execution_series_id": source.execution_series_id,
        }
    )
    return effective

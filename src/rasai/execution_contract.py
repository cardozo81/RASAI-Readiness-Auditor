"""Canonical validation boundary for durable control-plane execution payloads."""
from __future__ import annotations

from typing import Any, Mapping

from rasai.audit_execution_contract import normalize_audit_job_payload

SUPPORTED_EXECUTION_JOB_TYPES = frozenset({"AUDIT", "AUDIT_REPROCESS", "SEARCH_MONITOR", "REPORT_REFRESH"})


def validate_execution_job_payload(job_type: str, payload: Mapping[str, Any]) -> None:
    """Validate a secret-free durable payload without materializing defaults into storage.

    Durable jobs intentionally persist only the user's explicit choices. Runtime defaults
    are resolved later from the canonical contracts, which prevents SaaS payload drift and
    preserves the distinction between omitted defaults and explicit customization.
    """
    normalized_type = str(job_type).strip().upper()
    if normalized_type not in SUPPORTED_EXECUTION_JOB_TYPES:
        raise ValueError(f"unsupported execution job type: {job_type}")

    if normalized_type == "AUDIT":
        normalize_audit_job_payload(payload)
        return

    if normalized_type == "AUDIT_REPROCESS":
        allowed = {"audit_id", "status_only"}
        if set(payload) - allowed:
            raise ValueError("AUDIT_REPROCESS accepts only payload.audit_id and payload.status_only")
        audit_id = payload.get("audit_id")
        if not isinstance(audit_id, str) or not audit_id.strip().upper().startswith("AUD-"):
            raise ValueError("AUDIT_REPROCESS requires a valid payload.audit_id")
        status_only = payload.get("status_only", False)
        if not isinstance(status_only, bool):
            raise ValueError("AUDIT_REPROCESS payload.status_only must be boolean")
        return

    if normalized_type == "SEARCH_MONITOR":
        if set(payload) != {"query_id"}:
            raise ValueError("SEARCH_MONITOR execution accepts only payload.query_id")
        query_id = payload.get("query_id")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("SEARCH_MONITOR execution requires a non-empty payload.query_id")
        return

    if set(payload) - {"surface"}:
        raise ValueError("REPORT_REFRESH execution accepts only payload.surface")
    surface = payload.get("surface", "portfolio")
    if not isinstance(surface, str) or surface.strip() != "portfolio":
        raise ValueError("REPORT_REFRESH currently supports only payload.surface=portfolio")

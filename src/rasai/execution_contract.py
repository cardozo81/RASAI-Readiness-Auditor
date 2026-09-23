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
        allowed = {
            "audit_id",
            "status_only",
            "selected_items",
            "use_ai",
            "ai_provider",
            "ai_model",
            "ai_reasoning",
        }
        if set(payload) - allowed:
            raise ValueError("AUDIT_REPROCESS contém campos não suportados")
        audit_id = payload.get("audit_id")
        if not isinstance(audit_id, str) or not audit_id.strip().upper().startswith("AUD-"):
            raise ValueError("AUDIT_REPROCESS requires a valid payload.audit_id")
        status_only = payload.get("status_only", False)
        if not isinstance(status_only, bool):
            raise ValueError("AUDIT_REPROCESS payload.status_only must be boolean")
        selected = payload.get("selected_items")
        if selected is not None:
            if not isinstance(selected, list) or not selected:
                raise ValueError("AUDIT_REPROCESS selected_items deve ser uma lista não vazia")
            if any(not isinstance(item, (str, dict)) for item in selected):
                raise ValueError("AUDIT_REPROCESS selected_items aceita texto ou objeto por item")
        use_ai = payload.get("use_ai")
        if use_ai is not None and not isinstance(use_ai, bool):
            raise ValueError("AUDIT_REPROCESS payload.use_ai deve ser booleano")
        for name in ("ai_provider", "ai_model", "ai_reasoning"):
            value = payload.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"AUDIT_REPROCESS payload.{name} deve ser texto")
        return

    if normalized_type == "SEARCH_MONITOR":
        if set(payload) != {"query_id"}:
            raise ValueError("SEARCH_MONITOR execution accepts only payload.query_id")
        query_id = payload.get("query_id")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("SEARCH_MONITOR execution requires a non-empty payload.query_id")
        return

    surface = payload.get("surface", "portfolio")
    if not isinstance(surface, str):
        raise ValueError("REPORT_REFRESH payload.surface deve ser texto")
    normalized_surface = surface.strip().casefold()
    if normalized_surface == "portfolio":
        if set(payload) - {"surface"}:
            raise ValueError("REPORT_REFRESH de portfólio aceita somente payload.surface")
        return
    if normalized_surface != "consolidated":
        raise ValueError("REPORT_REFRESH aceita as superfícies portfolio ou consolidated")

    allowed = {
        "surface",
        "baseline_audit_id",
        "current_audit_id",
        "selection_mode",
        "audit_ids",
        "use_ai",
        "ai_provider",
        "ai_model",
        "ai_reasoning",
        "ai_timeout_seconds",
    }
    if set(payload) - allowed:
        raise ValueError("REPORT_REFRESH consolidado contém campos não suportados")

    baseline = payload.get("baseline_audit_id")
    current = payload.get("current_audit_id")
    if not isinstance(baseline, str) or not baseline.strip().upper().startswith("AUD-"):
        raise ValueError("relatório consolidado exige payload.baseline_audit_id")
    if not isinstance(current, str) or not current.strip().upper().startswith("AUD-"):
        raise ValueError("relatório consolidado exige payload.current_audit_id")
    if baseline.strip() == current.strip():
        raise ValueError("baseline_audit_id e current_audit_id devem ser distintos")

    selection_mode = str(payload.get("selection_mode") or "ALL").strip().upper()
    if selection_mode not in {"ALL", "SUCCESS_ONLY", "MANUAL"}:
        raise ValueError("selection_mode deve ser ALL, SUCCESS_ONLY ou MANUAL")

    audit_ids = payload.get("audit_ids", [])
    if not isinstance(audit_ids, list) or any(
        not isinstance(item, str) or not item.strip().upper().startswith("AUD-")
        for item in audit_ids
    ):
        raise ValueError("audit_ids deve ser uma lista de IDs AUD-*")

    use_ai = payload.get("use_ai", False)
    if not isinstance(use_ai, bool):
        raise ValueError("use_ai deve ser booleano")
    provider = payload.get("ai_provider")
    if provider is not None and not isinstance(provider, str):
        raise ValueError("ai_provider deve ser texto quando informado")
    # use_ai=true does not imply provider readiness. none/omitted is a materializable
    # requested-but-unavailable AI state for the deterministic consolidated report.

    timeout = payload.get("ai_timeout_seconds")
    if timeout is not None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= float(timeout) <= 600:
            raise ValueError("ai_timeout_seconds deve estar entre 1 e 600")


"""Consumption Analytics query and calendar-period contracts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from .saas_scheduling import normalize_timezone

_ALLOWED_GROUPS = {
    "workspace", "project", "property", "environment", "domain", "url", "user",
    "job_type", "provider", "integration", "category", "operation", "status", "model",
    "job", "audit", "resource",
}
_ALLOWED_PERIODS = {"TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_30_DAYS", "CURRENT_MONTH", "PREVIOUS_MONTH"}


def _parse_iso(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include an explicit timezone")
    return parsed.astimezone(UTC).isoformat()


def resolve_period(period: str, timezone: str, *, now: str | datetime | None = None) -> tuple[str, str]:
    key = str(period or "").strip().upper()
    if key not in _ALLOWED_PERIODS:
        raise ValueError("period must be TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, CURRENT_MONTH or PREVIOUS_MONTH")
    zone = ZoneInfo(normalize_timezone(timezone))
    if now is None:
        instant = datetime.now(UTC)
    elif isinstance(now, datetime):
        if now.tzinfo is None:
            raise ValueError("period now must include an explicit timezone")
        instant = now.astimezone(UTC)
    else:
        parsed = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("period now must include an explicit timezone")
        instant = parsed.astimezone(UTC)
    local_now = instant.astimezone(zone)
    today = local_now.date()

    if key == "TODAY":
        start_day, end_day = today, today + timedelta(days=1)
    elif key == "YESTERDAY":
        start_day, end_day = today - timedelta(days=1), today
    elif key == "LAST_7_DAYS":
        start_day, end_day = today - timedelta(days=6), today + timedelta(days=1)
    elif key == "LAST_30_DAYS":
        start_day, end_day = today - timedelta(days=29), today + timedelta(days=1)
    elif key == "CURRENT_MONTH":
        start_day = today.replace(day=1)
        end_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        current_start = today.replace(day=1)
        previous_last = current_start - timedelta(days=1)
        start_day = previous_last.replace(day=1)
        end_day = current_start
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=zone).astimezone(UTC).isoformat()
    end = datetime.combine(end_day, datetime.min.time(), tzinfo=zone).astimezone(UTC).isoformat()
    return start, end


def usage_analytics(
    store: Any,
    organization_id: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    property_id: str | None = None,
    environment_id: str | None = None,
    domain: str | None = None,
    url: str | None = None,
    user_id: str | None = None,
    job_type: str | None = None,
    provider: str | None = None,
    integration: str | None = None,
    category: str | None = None,
    operation: str | None = None,
    status: str | None = None,
    model: str | None = None,
    resource_type: str | None = None,
    job_id: str | None = None,
    audit_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    group_by: Sequence[str] = ("category", "provider"),
    limit: int = 10000,
) -> dict[str, Any]:
    groups = tuple(dict.fromkeys(str(item).strip().lower() for item in group_by if str(item).strip()))
    invalid = sorted(set(groups) - _ALLOWED_GROUPS)
    if invalid:
        raise ValueError("unsupported usage group(s): " + ", ".join(invalid))
    start_iso = _parse_iso(start, field="start")
    end_iso = _parse_iso(end, field="end")
    if start_iso and end_iso and start_iso >= end_iso:
        raise ValueError("usage start must be earlier than end")

    projects = {item.project_id: item for item in store.list_projects()}
    workspaces = {item.workspace_id: item for item in store.list_workspaces()}
    if workspace_id:
        workspace = workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise ValueError("usage workspace is outside organization")
    if project_id:
        project = projects.get(project_id)
        if project is None:
            raise ValueError("usage project does not exist")
        workspace = workspaces.get(project.workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise ValueError("usage project is outside organization")
        if workspace_id and project.workspace_id != workspace_id:
            raise ValueError("usage project is outside workspace")

    clauses = ["organization_id=?"]
    values: list[Any] = [organization_id]
    for field, value in (("project_id", project_id), ("property_id", property_id), ("provider", provider), ("category", category), ("audit_id", audit_id)):
        if value:
            clauses.append(f"{field}=?")
            values.append(value)
    if start_iso:
        clauses.append("occurred_at>=?")
        values.append(start_iso)
    if end_iso:
        clauses.append("occurred_at<?")
        values.append(end_iso)
    bounded_limit = max(1, min(int(limit), 50000))
    sql = "SELECT * FROM usage_events WHERE " + " AND ".join(clauses) + " ORDER BY occurred_at DESC LIMIT ?"
    values.append(bounded_limit)
    rows = store._connection.execute(sql, values).fetchall()

    def load_json(value: Any) -> dict[str, Any]:
        import json
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value or "{}"))
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        metadata = load_json(item.pop("metadata_json", None))
        event_project = item.get("project_id")
        workspace = projects.get(str(event_project)).workspace_id if event_project and str(event_project) in projects else None
        dimensions = {
            "workspace": workspace,
            "project": event_project,
            "property": item.get("property_id"),
            "environment": metadata.get("environment_id"),
            "domain": metadata.get("domain"),
            "url": metadata.get("url"),
            "user": metadata.get("user_id"),
            "job_type": metadata.get("job_type"),
            "provider": item.get("provider"),
            "integration": metadata.get("integration") or (item.get("provider") if metadata.get("resource_type") == "INTEGRATION" else None),
            "category": item.get("category"),
            "operation": metadata.get("operation"),
            "status": metadata.get("status"),
            "model": metadata.get("model"),
            "job": metadata.get("job_id"),
            "audit": item.get("audit_id"),
            "resource": metadata.get("resource_type"),
        }
        checks = (
            (workspace_id, dimensions["workspace"]),
            (environment_id, dimensions["environment"]),
            (domain, dimensions["domain"]),
            (url, dimensions["url"]),
            (user_id, dimensions["user"]),
            (job_type, dimensions["job_type"]),
            (integration, dimensions["integration"]),
            (operation, dimensions["operation"]),
            (status, dimensions["status"]),
            (model, dimensions["model"]),
            (resource_type, dimensions["resource"]),
            (job_id, dimensions["job"]),
        )
        if any(expected is not None and str(actual or "") != str(expected) for expected, actual in checks):
            continue
        item["metadata"] = metadata
        item["dimensions"] = dimensions
        events.append(item)

    def blank() -> dict[str, Any]:
        return {
            "event_count": 0,
            "quantity_by_unit": {},
            "cost_by_currency": {},
            "cost_known_events": 0,
            "cost_unknown_events": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "retry_count": 0,
            "fallback_count": 0,
            "failure_count": 0,
            "duration_ms": 0,
        }

    def add(bucket: dict[str, Any], event: dict[str, Any]) -> None:
        bucket["event_count"] += 1
        unit = str(event.get("unit") or "unknown")
        bucket["quantity_by_unit"][unit] = bucket["quantity_by_unit"].get(unit, 0.0) + float(event.get("quantity") or 0.0)
        cost = event.get("cost_estimate")
        if cost is None:
            bucket["cost_unknown_events"] += 1
        else:
            bucket["cost_known_events"] += 1
            currency = str(event.get("currency") or "UNSPECIFIED")
            bucket["cost_by_currency"][currency] = bucket["cost_by_currency"].get(currency, 0.0) + float(cost)
        metadata = event["metadata"]
        for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "duration_ms"):
            value = metadata.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                bucket[key] += value
        decision = str(metadata.get("decision") or "").upper()
        bucket["retry_count"] += int(bool(metadata.get("retry")) or decision == "RETRY")
        bucket["fallback_count"] += int(bool(metadata.get("fallback_from_provider")) or decision.startswith("FALLBACK"))
        bucket["failure_count"] += int(str(metadata.get("status") or "").upper() in {"FAILED", "FAIL", "ERROR", "TIMEOUT", "CONTRACT_ERROR"})

    summary = blank()
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for event in events:
        add(summary, event)
        key = tuple(event["dimensions"].get(field) for field in groups)
        add(grouped.setdefault(key, blank()), event)
    group_rows = [{"dimensions": dict(zip(groups, key)), **bucket} for key, bucket in grouped.items()]
    group_rows.sort(key=lambda item: (-item["event_count"], str(item["dimensions"])))
    coverage = {
        "events": len(events),
        "with_workspace": sum(1 for item in events if item["dimensions"].get("workspace")),
        "with_url": sum(1 for item in events if item["dimensions"].get("url")),
        "with_user": sum(1 for item in events if item["dimensions"].get("user")),
        "with_environment": sum(1 for item in events if item["dimensions"].get("environment")),
        "with_provider": sum(1 for item in events if item.get("provider")),
        "with_cost": sum(1 for item in events if item.get("cost_estimate") is not None),
    }
    return {
        "summary": summary,
        "groups": group_rows,
        "coverage": coverage,
        "event_limit": bounded_limit,
        "filters": {
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "property_id": property_id,
            "environment_id": environment_id,
            "domain": domain,
            "url": url,
            "user_id": user_id,
            "job_type": job_type,
            "provider": provider,
            "integration": integration,
            "category": category,
            "operation": operation,
            "status": status,
            "model": model,
            "resource_type": resource_type,
            "job_id": job_id,
            "audit_id": audit_id,
            "start": start_iso,
            "end": end_iso,
        },
    }

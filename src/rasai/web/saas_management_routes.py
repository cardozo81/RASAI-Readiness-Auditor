"""Tenant-aware Scheduling Management and Consumption Analytics HTTP surfaces."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from rasai.audit_execution_contract import audit_job_options
from rasai.platform.consumption import resolve_period
from rasai.secret_safety import redact_text, redact_value

from .authz import (
    AuthorizationError,
    Principal,
    accessible_organization_ids,
    accessible_workspace_ids,
    require_execution_manage,
    require_project_read,
)
from .saas_management_ui import operations_ui_html


class RecurrenceRequest(BaseModel):
    times: list[str] = Field(default_factory=list, max_length=48)
    every_minutes: int | None = Field(default=None, ge=60, le=44640)
    window_start: str = "00:00"
    window_end: str = "23:59"
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    month_days: list[int] = Field(default_factory=list, max_length=31)
    last_day: bool = False


class ManagedScheduleCreate(BaseModel):
    property_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    job_type: Literal["AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"] = "AUDIT"
    recurrence: RecurrenceRequest
    timezone: str = Field(min_length=1, max_length=200)
    urls: list[str] = Field(default_factory=list, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    overlap_policy: Literal["SKIP", "QUEUE"] = "SKIP"
    priority: int = Field(default=100, ge=0, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=100)


class ManagedSchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    recurrence: RecurrenceRequest | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=200)
    urls: list[str] | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] | None = None
    overlap_policy: Literal["SKIP", "QUEUE"] | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    max_attempts: int | None = Field(default=None, ge=1, le=100)


class DuplicateScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _safe(value: Any) -> Any:
    return redact_value(value)


def _detail(exc: Exception) -> str:
    return redact_text(str(exc))


def _schedule_or_404(store: Any, schedule_id: str) -> dict[str, Any]:
    item = store.get_managed_schedule(schedule_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    return item


def _mutate(call: Callable[[], Any]) -> Any:
    try:
        return _safe(call())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc)) from exc


def install_saas_management_routes(
    app: Any,
    *,
    store_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
) -> None:
    @app.get("/api/v1/audit-job-options")
    def audit_options(
        _principal: Principal = Depends(principal_dependency),
    ) -> dict[str, Any]:
        options = [asdict(option) for option in audit_job_options()]
        return {
            "options": list(_safe(options)),
            "defaults": {item["name"]: item["default"] for item in options},
        }

    @app.get("/api/v1/projects/{project_id}/schedules")
    def schedules(
        project_id: str,
        property_id: str | None = None,
        environment_id: str | None = None,
        state: list[str] | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        try:
            return list(_safe(store.list_managed_schedules(
                project_id=project_id,
                property_id=property_id,
                environment_id=environment_id,
                statuses=state,
                limit=limit,
                offset=offset,
            )))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc

    @app.post("/api/v1/projects/{project_id}/schedules", status_code=status.HTTP_201_CREATED)
    def create_schedule(
        project_id: str,
        request: ManagedScheduleCreate,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        require_execution_manage(store, principal, project_id)
        data = request.model_dump()
        recurrence = data.pop("recurrence")
        return _mutate(lambda: store.create_managed_schedule(
            project_id=project_id,
            created_by=principal.user_id,
            recurrence=recurrence,
            **data,
        ))

    @app.get("/api/v1/schedules/{schedule_id}")
    def schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return dict(_safe(item))

    @app.patch("/api/v1/schedules/{schedule_id}")
    def patch_schedule(
        schedule_id: str,
        request: ManagedSchedulePatch,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        changes = request.model_dump(exclude_unset=True)
        if "recurrence" in changes and changes["recurrence"] is not None:
            changes["recurrence"] = dict(changes["recurrence"])
        return _mutate(lambda: store.update_managed_schedule(
            schedule_id,
            actor_user_id=principal.user_id,
            **changes,
        ))

    @app.post("/api/v1/schedules/{schedule_id}/pause")
    def pause_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "PAUSED", actor_user_id=principal.user_id))

    @app.post("/api/v1/schedules/{schedule_id}/resume")
    def resume_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "ACTIVE", actor_user_id=principal.user_id))

    @app.delete("/api/v1/schedules/{schedule_id}")
    def disable_schedule(
        schedule_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.set_managed_schedule_status(schedule_id, "DISABLED", actor_user_id=principal.user_id))

    @app.post("/api/v1/schedules/{schedule_id}/duplicate", status_code=status.HTTP_201_CREATED)
    def duplicate_schedule(
        schedule_id: str,
        request: DuplicateScheduleRequest,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_execution_manage(store, principal, item["project_id"])
        return _mutate(lambda: store.duplicate_managed_schedule(
            schedule_id, name=request.name, actor_user_id=principal.user_id
        ))

    @app.get("/api/v1/schedules/{schedule_id}/runs")
    def schedule_runs(
        schedule_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return list(_safe(store.list_schedule_runs(schedule_id, limit=limit)))

    @app.get("/api/v1/schedules/{schedule_id}/events")
    def schedule_events(
        schedule_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return list(_safe(store.list_schedule_events(schedule_id, limit=limit)))

    @app.get("/api/v1/schedules/{schedule_id}/next-occurrences")
    def next_schedule_occurrences(
        schedule_id: str,
        count: int = Query(default=10, ge=1, le=100),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = _schedule_or_404(store, schedule_id)
        require_project_read(store, principal, item["project_id"])
        return {"schedule_id": schedule_id, "occurrences": list(store.schedule_next_occurrences(schedule_id, count=count))}

    @app.get("/api/v1/organizations/{organization_id}/consumption")
    def consumption(
        organization_id: str,
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
        event_status: str | None = None,
        model: str | None = None,
        resource_type: str | None = None,
        job_id: str | None = None,
        audit_id: str | None = None,
        period: str | None = None,
        timezone: str | None = None,
        start: str | None = None,
        end: str | None = None,
        group_by: str = "category,provider",
        limit: int = Query(default=10000, ge=1, le=50000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        if organization_id not in accessible_organization_ids(store, principal):
            raise AuthorizationError("organization is outside the caller tenancy scope")
        if workspace_id and workspace_id not in accessible_workspace_ids(store, principal):
            raise AuthorizationError("workspace is outside the caller tenancy scope")
        if project_id:
            require_project_read(store, principal, project_id)
        if period:
            if start or end:
                raise HTTPException(status_code=422, detail="period cannot be combined with start/end")
            try:
                start, end = resolve_period(period, timezone or "UTC")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=_detail(exc)) from exc
        groups = tuple(item.strip() for item in group_by.split(",") if item.strip())
        try:
            return dict(_safe(store.usage_analytics(
                organization_id,
                workspace_id=workspace_id,
                project_id=project_id,
                property_id=property_id,
                environment_id=environment_id,
                domain=domain,
                url=url,
                user_id=user_id,
                job_type=job_type,
                provider=provider,
                integration=integration,
                category=category,
                operation=operation,
                status=event_status,
                model=model,
                resource_type=resource_type,
                job_id=job_id,
                audit_id=audit_id,
                start=start,
                end=end,
                group_by=groups,
                limit=limit,
            )))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=_detail(exc)) from exc

    @app.get("/app/operations", response_class=HTMLResponse, include_in_schema=False)
    def operations_ui() -> HTMLResponse:
        return HTMLResponse(operations_ui_html(), headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        })

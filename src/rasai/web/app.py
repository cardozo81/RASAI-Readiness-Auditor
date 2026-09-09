"""FastAPI adapter over the canonical RASAi control plane.

The HTTP layer is intentionally thin: domain persistence, tenancy and Search
Monitoring contracts remain owned by their existing modules. The API never executes
audits inside the request process; execution endpoints only enqueue durable jobs.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from rasai.platform.database import open_platform_store, resolve_platform_database_config
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository
from rasai.secret_safety import redact_value

from .auth import ApiAuthSettings, PrincipalResolver, build_principal_resolver
from .authz import (
    AuthorizationError,
    Principal,
    accessible_organization_ids,
    accessible_project_ids,
    accessible_workspace_ids,
    require_execution_create,
    require_execution_manage,
    require_project_read,
)


@dataclass(frozen=True, slots=True)
class ApiSettings:
    audits_root: Path = Path("audits")
    docs_enabled: bool = False
    auth: ApiAuthSettings = ApiAuthSettings()

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        docs = os.getenv("RASAI_API_DOCS_ENABLED", "0").strip().casefold() in {"1", "true", "yes", "on"}
        return cls(
            audits_root=Path(os.getenv("RASAI_API_AUDITS_ROOT", "audits")),
            docs_enabled=docs,
            auth=ApiAuthSettings.from_environment(),
        )


class ExecutionJobCreate(BaseModel):
    property_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    job_type: Literal["AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"]
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    priority: int = Field(default=100, ge=0, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=100)


StoreFactory = Callable[[], Any]
SearchRepositoryFactory = Callable[[], Any]


def _safe(value: Any) -> Any:
    sanitized = redact_value(value)
    return sanitized


def _model(item: Any) -> dict[str, Any]:
    return dict(_safe(asdict(item)))


def _audit_projection(item: Any) -> dict[str, Any]:
    return dict(_safe({
        "audit_id": item.audit_id,
        "property_id": item.property_id,
        "environment_id": item.environment_id,
        "event_time": item.event_time,
        "status": item.status,
        "completion_status": item.completion_status,
        "project_name": item.project_name,
        "auditor_version": item.auditor_version,
        "ruleset_version": item.ruleset_version,
        "scoring_versions": list(item.scoring_versions),
        "domains": list(item.domains),
        "devices": list(item.devices),
        "url_count": item.url_count,
        "indexed_at": item.indexed_at,
    }))


def create_app(
    settings: ApiSettings | None = None,
    *,
    store_factory: StoreFactory | None = None,
    search_repository_factory: SearchRepositoryFactory | None = None,
    principal_resolver: PrincipalResolver | None = None,
) -> FastAPI:
    config = settings or ApiSettings.from_environment()
    docs_url = "/docs" if config.docs_enabled else None
    openapi_url = "/openapi.json" if config.docs_enabled else None
    app = FastAPI(
        title="RASAi Control Plane API",
        version="1",
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )

    def default_store_factory() -> Any:
        return open_platform_store(audits_root=config.audits_root)

    def default_search_repository_factory() -> Any:
        return open_search_monitoring_repository(audits_root=config.audits_root)

    app.state.store_factory = store_factory or default_store_factory
    app.state.search_repository_factory = search_repository_factory or default_search_repository_factory
    app.state.principal_resolver = principal_resolver or build_principal_resolver(config.auth)
    app.state.settings = config

    def store_dependency() -> Iterator[Any]:
        store = app.state.store_factory()
        try:
            yield store
        finally:
            store.close()

    def search_repository_dependency() -> Iterator[Any]:
        repository = app.state.search_repository_factory()
        try:
            yield repository
        finally:
            repository.close()

    async def principal_dependency(request: Request) -> Principal:
        return await app.state.principal_resolver(request)

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(_request: Request, exc: AuthorizationError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok", "service": "rasai-api"}

    @app.get("/health/ready")
    def ready() -> dict[str, Any]:
        try:
            with app.state.store_factory() as store:
                if hasattr(store, "health"):
                    health = store.health()
                    return {"status": "ready", "control_plane": _safe(health)}
                database_config = resolve_platform_database_config(audits_root=config.audits_root)
                return {
                    "status": "ready",
                    "control_plane": {
                        "backend": database_config.backend,
                        "database": database_config.display,
                        "counts": _safe(store.counts()),
                    },
                }
        except Exception as exc:
            from rasai.secret_safety import redact_text
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=redact_text(str(exc)),
            ) from exc

    @app.get("/api/v1/me")
    def me(
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        memberships = [
            {
                "membership_id": item.get("membership_id"),
                "organization_id": item.get("organization_id"),
                "workspace_id": item.get("workspace_id"),
                "project_id": item.get("project_id"),
                "role": item.get("role"),
            }
            for item in store.list_memberships(user_id=principal.user_id)
        ]
        if not memberships:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no active RASAi membership")
        return {
            "user_id": principal.user_id,
            "organization_ids": sorted(accessible_organization_ids(store, principal)),
            "workspace_ids": sorted(accessible_workspace_ids(store, principal)),
            "project_ids": sorted(accessible_project_ids(store, principal)),
            "memberships": _safe(memberships),
        }

    @app.get("/api/v1/organizations")
    def organizations(
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        allowed = accessible_organization_ids(store, principal)
        return [_model(item) for item in store.list_organizations() if item.organization_id in allowed]

    @app.get("/api/v1/organizations/{organization_id}/workspaces")
    def workspaces(
        organization_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        if organization_id not in accessible_organization_ids(store, principal):
            raise AuthorizationError("organization is outside the caller tenancy scope")
        allowed = accessible_workspace_ids(store, principal)
        return [
            _model(item)
            for item in store.list_workspaces(organization_id)
            if item.workspace_id in allowed
        ]

    @app.get("/api/v1/workspaces/{workspace_id}/projects")
    def projects(
        workspace_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        if workspace_id not in accessible_workspace_ids(store, principal):
            raise AuthorizationError("workspace is outside the caller tenancy scope")
        allowed = accessible_project_ids(store, principal)
        return [_model(item) for item in store.list_projects(workspace_id) if item.project_id in allowed]

    @app.get("/api/v1/projects/{project_id}/properties")
    def properties(
        project_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        return [_model(item) for item in store.list_properties(project_id)]

    @app.get("/api/v1/properties/{property_id}/environments")
    def environments(
        property_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        prop = next((item for item in store.list_properties() if item.property_id == property_id), None)
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found")
        require_project_read(store, principal, prop.project_id)
        return [_model(item) for item in store.list_environments(property_id)]

    @app.get("/api/v1/projects/{project_id}/audits")
    def audits(
        project_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        audit_by_id: dict[str, Any] = {}
        for prop in store.list_properties(project_id):
            for audit in store.list_audits(property_id=prop.property_id):
                audit_by_id[audit.audit_id] = audit
        return [
            _audit_projection(item)
            for item in sorted(audit_by_id.values(), key=lambda value: value.event_time, reverse=True)
        ]

    @app.get("/api/v1/projects/{project_id}/search-queries")
    def search_queries(
        project_id: str,
        enabled_only: bool = False,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
        repository: Any = Depends(search_repository_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        return [
            _model(item)
            for item in repository.list_queries(enabled_only=enabled_only)
            if item.project_id == project_id
        ]

    @app.get("/api/v1/search-queries/{query_id}/runs")
    def search_query_runs(
        query_id: str,
        limit: int = Query(default=20, ge=1, le=200),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
        repository: Any = Depends(search_repository_dependency),
    ) -> list[dict[str, Any]]:
        query = repository.get_query(query_id)
        if query is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="search query not found")
        require_project_read(store, principal, query.project_id)
        return [_model(item) for item in repository.list_runs(query_id, limit=limit)]

    @app.get("/api/v1/projects/{project_id}/execution-jobs")
    def execution_jobs(
        project_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        return [_model(item) for item in store.list_execution_jobs(project_id=project_id, limit=limit)]

    @app.post("/api/v1/projects/{project_id}/execution-jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_execution_job(
        project_id: str,
        request: ExecutionJobCreate,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        require_execution_create(store, principal, project_id)
        try:
            item = store.enqueue_execution_job(
                project_id=project_id,
                property_id=request.property_id,
                environment_id=request.environment_id,
                job_type=request.job_type,
                payload=request.payload,
                requested_by=principal.user_id,
                idempotency_key=request.idempotency_key,
                priority=request.priority,
                max_attempts=request.max_attempts,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return _model(item)

    @app.get("/api/v1/execution-jobs/{job_id}")
    def execution_job(
        job_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = store.get_execution_job(job_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution job not found")
        require_project_read(store, principal, item.project_id)
        return _model(item)

    @app.post("/api/v1/execution-jobs/{job_id}/cancel")
    def cancel_execution_job(
        job_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        item = store.get_execution_job(job_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution job not found")
        require_execution_manage(store, principal, item.project_id)
        try:
            return _model(store.cancel_execution_job(job_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return app


app = create_app()

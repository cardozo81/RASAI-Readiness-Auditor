"""FastAPI adapter over the canonical RASAi control plane.

The HTTP layer is intentionally thin: domain persistence, tenancy and Search
Monitoring contracts remain owned by their existing modules. The API never executes
audits inside the request process; execution endpoints only enqueue durable jobs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.selection import candidate_audits, list_consolidated_history
from rasai.audit_configuration_reuse_saas import (
    assert_client_payload_has_no_provenance,
    build_reused_payload,
    install as install_audit_configuration_reuse_saas,
)
from rasai.platform.database import open_platform_store, resolve_platform_database_config
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository
from rasai.secret_safety import redact_text, redact_value

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
    source_audit_id: str | None = Field(default=None, min_length=5, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)
    priority: int = Field(default=100, ge=0, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=100)


class ConsolidatedReportCreate(BaseModel):
    property_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    baseline_audit_id: str = Field(min_length=5, max_length=200)
    current_audit_id: str = Field(min_length=5, max_length=200)
    selection_mode: Literal["ALL", "SUCCESS_ONLY", "MANUAL"] = "ALL"
    audit_ids: list[str] = Field(default_factory=list)
    use_ai: bool = False
    ai_provider: str | None = Field(default=None, max_length=100)
    ai_model: str | None = Field(default=None, max_length=200)
    ai_reasoning: str | None = Field(default=None, max_length=64)
    ai_timeout_seconds: float = Field(default=180.0, ge=1.0, le=600.0)
    idempotency_key: str | None = Field(default=None, max_length=200)


StoreFactory = Callable[[], Any]
SearchRepositoryFactory = Callable[[], Any]


def _safe(value: Any) -> Any:
    return redact_value(value)


def _detail(value: Any) -> str:
    return redact_text(str(value))


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


def _authorized_audit_ids(
    store: Any,
    project_id: str,
    *,
    property_id: str | None = None,
    environment_id: str | None = None,
) -> tuple[str, ...]:
    values: list[str] = []
    for prop in store.list_properties(project_id):
        if property_id and prop.property_id != property_id:
            continue
        for audit in store.list_audits(
            property_id=prop.property_id,
            environment_id=environment_id,
        ):
            values.append(str(audit.audit_id))
    return tuple(dict.fromkeys(values))


def create_app(
    settings: ApiSettings | None = None,
    *,
    store_factory: StoreFactory | None = None,
    search_repository_factory: SearchRepositoryFactory | None = None,
    principal_resolver: PrincipalResolver | None = None,
) -> FastAPI:
    # Extend the already-installed AUDIT contract with server-managed provenance
    # before any HTTP request can enqueue a durable job.
    install_audit_configuration_reuse_saas()
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
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": _detail(exc)})

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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_detail(exc),
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

    @app.get("/api/v1/projects/{project_id}/consolidated-report-candidates")
    def consolidated_report_candidates(
        project_id: str,
        property_id: str = Query(min_length=1, max_length=200),
        environment_id: str = Query(min_length=1, max_length=200),
        q: str | None = Query(default=None, max_length=4000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        prop = next(
            (item for item in store.list_properties(project_id) if item.property_id == property_id),
            None,
        )
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="propriedade não encontrada")
        environment = next(
            (item for item in store.list_environments(property_id) if item.environment_id == environment_id),
            None,
        )
        if environment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ambiente não encontrado")
        authorized = _authorized_audit_ids(
            store,
            project_id,
            property_id=property_id,
            environment_id=environment_id,
        )
        index = ConsolidationIndex(config.audits_root)
        index.refresh()
        return [
            {
                "audit_id": item.audit_id,
                "event_time": item.event_time,
                "url": item.url,
                "domain": item.domain,
                "device": item.device,
                "status": item.status,
                "completion_status": item.completion_status,
            }
            for item in candidate_audits(index, allowed_audit_ids=authorized, query=q)
        ]

    @app.get("/api/v1/projects/{project_id}/consolidated-reports")
    def consolidated_reports(
        project_id: str,
        q: str | None = Query(default=None, max_length=4000),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        authorized = _authorized_audit_ids(store, project_id)
        return [
            {
                "cons_id": item.cons_id,
                "generated_at": item.generated_at,
                "url": item.url,
                "domain": item.domain,
                "device": item.device,
                "period_start": item.period_start,
                "period_end": item.period_end,
                "audit_ids": list(item.audit_ids),
                "audit_count": item.audit_count,
                "selection_mode": item.selection_mode,
                "generation_mode": item.generation_mode,
                "ai_status": item.ai_status,
                "confidence": item.confidence,
            }
            for item in list_consolidated_history(
                config.audits_root,
                query=q,
                allowed_audit_ids=authorized,
            )
        ]

    @app.get("/api/v1/projects/{project_id}/consolidated-reports/{cons_id}/result")
    def consolidated_report_result(
        project_id: str,
        cons_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> FileResponse:
        require_project_read(store, principal, project_id)
        authorized = _authorized_audit_ids(store, project_id)
        item = next(
            (
                value for value in list_consolidated_history(
                    config.audits_root,
                    allowed_audit_ids=authorized,
                )
                if value.cons_id == cons_id
            ),
            None,
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="relatório consolidado não encontrado")
        return FileResponse(
            item.report_path,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/projects/{project_id}/consolidated-reports", status_code=status.HTTP_202_ACCEPTED)
    def create_consolidated_report(
        project_id: str,
        request: ConsolidatedReportCreate,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        require_execution_create(store, principal, project_id)
        prop = next(
            (item for item in store.list_properties(project_id) if item.property_id == request.property_id),
            None,
        )
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="propriedade não encontrada")
        environment = next(
            (item for item in store.list_environments(request.property_id) if item.environment_id == request.environment_id),
            None,
        )
        if environment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ambiente não encontrado")

        provider = str(request.ai_provider or "").strip().casefold()
        # A solicitação da camada de IA e a disponibilidade do provider são estados
        # distintos. Sem provider, o worker materializa o CONS determinístico e
        # registra NOT_CONFIGURED sem efetuar chamada externa.

        authorized = _authorized_audit_ids(
            store,
            project_id,
            property_id=request.property_id,
            environment_id=request.environment_id,
        )
        requested_ids = {
            request.baseline_audit_id,
            request.current_audit_id,
            *(str(item).strip() for item in request.audit_ids if str(item).strip()),
        }
        if not requested_ids.issubset(set(authorized)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="uma ou mais auditorias selecionadas não pertencem ao escopo autorizado",
            )

        payload: dict[str, Any] = {
            "surface": "consolidated",
            "baseline_audit_id": request.baseline_audit_id,
            "current_audit_id": request.current_audit_id,
            "selection_mode": request.selection_mode,
            "use_ai": bool(request.use_ai),
            "ai_timeout_seconds": request.ai_timeout_seconds,
        }
        if request.selection_mode == "MANUAL":
            payload["audit_ids"] = list(request.audit_ids)
        if request.use_ai:
            payload["ai_provider"] = provider or "none"
            if request.ai_model:
                payload["ai_model"] = request.ai_model.strip()
            if request.ai_reasoning:
                payload["ai_reasoning"] = request.ai_reasoning.strip().upper()
        try:
            item = store.enqueue_execution_job(
                project_id=project_id,
                property_id=request.property_id,
                environment_id=request.environment_id,
                job_type="REPORT_REFRESH",
                payload=payload,
                requested_by=principal.user_id,
                idempotency_key=request.idempotency_key,
                priority=100,
                max_attempts=3,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc)) from exc
        response = _model(item)
        response["report_kind"] = "Relatório consolidado longitudinal"
        response["selection_request"] = {
            "baseline_audit_id": request.baseline_audit_id,
            "current_audit_id": request.current_audit_id,
            "selection_mode": request.selection_mode,
            "manual_audit_ids": list(request.audit_ids) if request.selection_mode == "MANUAL" else [],
            "use_ai": bool(request.use_ai),
        }
        return response

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
            if request.source_audit_id and request.job_type != "AUDIT":
                raise ValueError("source_audit_id is supported only for AUDIT jobs")
            if request.job_type == "AUDIT":
                assert_client_payload_has_no_provenance(request.payload)
            effective_payload = request.payload
            if request.source_audit_id:
                effective_payload = build_reused_payload(
                    str(config.audits_root),
                    request.source_audit_id,
                    request.payload,
                    project_id=project_id,
                    property_id=request.property_id,
                    environment_id=request.environment_id,
                )
            item = store.enqueue_execution_job(
                project_id=project_id,
                property_id=request.property_id,
                environment_id=request.environment_id,
                job_type=request.job_type,
                payload=effective_payload,
                requested_by=principal.user_id,
                idempotency_key=request.idempotency_key,
                priority=request.priority,
                max_attempts=request.max_attempts,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc)) from exc
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

    @app.get("/api/v1/execution-jobs/{job_id}/result")
    def execution_job_result(
        job_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> FileResponse:
        item = store.get_execution_job(job_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution job not found")
        require_project_read(store, principal, item.project_id)
        payload = item.payload if isinstance(item.payload, dict) else {}
        if item.job_type != "REPORT_REFRESH" or str(payload.get("surface") or "").casefold() != "consolidated":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resultado consolidado não disponível para este job")
        if str(item.status).upper() != "SUCCEEDED" or not item.result_ref:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="relatório consolidado ainda não está disponível")

        allowed_root = (config.audits_root / "consolidated").resolve()
        target = (config.audits_root / str(item.result_ref)).resolve()
        try:
            target.relative_to(allowed_root)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="referência de relatório inválida") from exc
        if target.name != "report.html" or not target.parent.name.startswith("CONS-") or not target.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="relatório consolidado não encontrado")
        return FileResponse(
            target,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_detail(exc)) from exc

    return app


app = create_app()

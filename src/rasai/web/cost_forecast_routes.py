"""Tenant-aware pre-execution monetary cost forecast endpoint."""
from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from rasai.cost_forecast import forecast_saas_cost
from rasai.secret_safety import redact_text, redact_value

from .authz import Principal, require_execution_create


class ExecutionCostEstimateRequest(BaseModel):
    property_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    job_type: Literal["AUDIT", "SEARCH_MONITOR", "REPORT_REFRESH"] = "AUDIT"
    payload: dict[str, Any] = Field(default_factory=dict)


def _safe(value: Any) -> Any:
    return redact_value(value)


def install_cost_forecast_routes(
    app: Any,
    *,
    store_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
) -> None:
    @app.post("/api/v1/projects/{project_id}/execution-cost-estimate")
    def execution_cost_estimate(
        project_id: str,
        request: ExecutionCostEstimateRequest,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        require_execution_create(store, principal, project_id)
        if request.job_type != "AUDIT":
            return {
                "available": False,
                "show_confirmation": False,
                "confidence": "NENHUMA",
                "source": "saas-usage-ledger",
                "notes": ["não há estimador monetário canônico para este tipo de execução"],
            }

        prop = next(
            (item for item in store.list_properties(project_id) if item.property_id == request.property_id),
            None,
        )
        if prop is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="property is outside the selected project",
            )
        environment = next(
            (
                item
                for item in store.list_environments(request.property_id)
                if item.environment_id == request.environment_id
            ),
            None,
        )
        if environment is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="environment is outside the selected property",
            )

        project = next((item for item in store.list_projects() if item.project_id == project_id), None)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        workspace = next(
            (item for item in store.list_workspaces() if item.workspace_id == project.workspace_id),
            None,
        )
        if workspace is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        try:
            forecast = forecast_saas_cost(
                store,
                organization_id=workspace.organization_id,
                project_id=project_id,
                property_id=request.property_id,
                environment_id=request.environment_id,
                payload=request.payload,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=redact_text(str(exc)),
            ) from exc
        return dict(_safe(forecast.as_dict()))

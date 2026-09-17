"""Tenant-safe HTTP surface for reusable property semantic profiles."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from rasai.secret_safety import redact_text, redact_value

from .authz import Principal, require_execution_manage, require_project_read


class PropertySemanticProfileRequest(BaseModel):
    business_sector: str = Field(default="auto", max_length=200)
    business_description: str = Field(default="auto", max_length=2000)
    primary_offering: str = Field(default="auto", max_length=500)
    target_audience_profile: str = Field(default="auto", max_length=1000)
    primary_goal: str = Field(default="auto", max_length=500)
    positioning: str = Field(default="auto", max_length=1000)
    expected_revision: int | None = Field(default=None, ge=0)


def _safe(value: Any) -> Any:
    return redact_value(value)


def _detail(exc: Exception) -> str:
    return redact_text(str(exc))


def _property_project_id(store: Any, property_id: str) -> str:
    try:
        row = store.hierarchy_for_property(property_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found") from exc
    return str(row["project_id"])


def install_property_semantic_profile_routes(
    app: Any,
    *,
    store_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
) -> None:
    @app.get("/api/v1/properties/{property_id}/semantic-profile")
    def get_semantic_profile(
        property_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        project_id = _property_project_id(store, property_id)
        require_project_read(store, principal, project_id)
        return dict(_safe(store.get_property_semantic_profile(property_id)))

    @app.put("/api/v1/properties/{property_id}/semantic-profile")
    def put_semantic_profile(
        property_id: str,
        request: PropertySemanticProfileRequest,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        project_id = _property_project_id(store, property_id)
        require_execution_manage(store, principal, project_id)
        values = request.model_dump()
        expected_revision = values.pop("expected_revision")
        try:
            result = store.set_property_semantic_profile(
                property_id,
                updated_by=principal.user_id,
                expected_revision=expected_revision,
                **values,
            )
        except ValueError as exc:
            message = _detail(exc)
            code = status.HTTP_409_CONFLICT if "revision conflict" in message else status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=code, detail=message) from exc
        return dict(_safe(result))

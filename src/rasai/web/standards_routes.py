"""Authenticated SaaS catalog for standards/metrics capabilities.

Credential values are never returned. The state reflects the API process environment
and is therefore a capability hint; production deployments may have worker-specific
secret injection and should expose that distinction operationally.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from fastapi import Depends

from rasai.standards_service_registry import service_state, services

from .authz import Principal


def install_standards_routes(
    app: Any,
    *,
    principal_dependency: Callable[..., Any],
) -> None:
    @app.get("/api/v1/standards/services")
    def standards_services(
        _principal: Principal = Depends(principal_dependency),
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for item in services():
            state = service_state(item)
            metadata = asdict(item)
            metadata.pop("credential_envs", None)
            rows.append({
                **metadata,
                "credential_envs": list(item.credential_envs),
                "state": state["state"],
                "requested": state["requested"],
                "configured": state["configured"],
                "effective_enabled": state["effective_enabled"],
                "configuration_source": state["configuration_source"],
            })
        return {
            "services": rows,
            "capability_scope": "API_PROCESS_ENVIRONMENT_HINT",
            "secrets_exposed": False,
            "note": (
                "Credential values are never returned. Worker deployments can inject "
                "credentials independently from the API process."
            ),
        }

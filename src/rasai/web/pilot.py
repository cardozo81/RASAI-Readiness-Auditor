"""SaaS pilot routes layered on top of the existing tenant-aware control plane.

This module deliberately contains no scoring, crawling, Search Intelligence or audit
business logic. It exposes read projections and durable execution controls that are
already owned by the core/control-plane layers.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from rasai.platform.deployment import resolve_deployment_pair
from rasai.secret_safety import redact_value

from .authz import AuthorizationError, Principal, accessible_organization_ids, require_project_read
from .ui import PILOT_UI_HTML

_ALLOWED_REPORT_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
}

_CANONICAL_REPORT_PAGES = (
    ("index.html", "Visão geral"),
    ("readiness.html", "Readiness SARI"),
    ("scoring.html", "Metodologia de scoring"),
    ("mobile.html", "Relatório Mobile"),
    ("desktop.html", "Relatório Desktop"),
    ("remediation.html", "Remediações"),
    ("content-suggestions.html", "Conteúdo e JSON-LD"),
    ("crawling-discovery.html", "Rastreamento e descoberta"),
    ("accessibility.html", "Acessibilidade"),
    ("web-performance.html", "Web Performance"),
    ("search-intelligence.html", "Search Intelligence"),
    ("apdex.html", "Apdex de navegação"),
    ("apdex-experience.html", "Apdex de experiência"),
    ("ai-visibility.html", "Visibilidade em IA"),
    ("observability.html", "Search & AI observados"),
    ("quality.html", "Quality & decisão"),
    ("ai-usage.html", "Uso de IA"),
    ("references.html", "Referências e metodologia"),
)


def _safe(value: Any) -> Any:
    return redact_value(value)


def _model(value: Any) -> dict[str, Any]:
    return dict(_safe(asdict(value)))


def _authorized_audit(store: Any, principal: Principal, audit_id: str) -> Any:
    audit = store.get_audit(audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit not found")
    prop = next((item for item in store.list_properties() if item.property_id == audit.property_id), None)
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit property not found")
    require_project_read(store, principal, prop.project_id)
    return audit


def _report_root(audit: Any) -> Path:
    return (Path(audit.workspace_path).resolve() / "report").resolve()


def _report_asset(root: Path, asset_path: str) -> Path:
    relative = Path(asset_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report asset not found")
    if relative.suffix.casefold() not in _ALLOWED_REPORT_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report asset not found")
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report asset not found")
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report asset not found")
    return candidate


def install_pilot_routes(
    app: Any,
    *,
    store_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
) -> None:
    """Install the browser pilot and additive API projections on ``app``."""

    @app.get("/app", response_class=HTMLResponse, include_in_schema=False)
    async def pilot_ui(request: Request) -> HTMLResponse | RedirectResponse:
        if request.app.state.settings.auth.mode == "oidc":
            try:
                await request.app.state.principal_resolver(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)
                raise
        return HTMLResponse(
            PILOT_UI_HTML,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'self'"
                ),
            },
        )

    @app.get("/api/v1/projects/{project_id}/milestones")
    def project_milestones(
        project_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        require_project_read(store, principal, project_id)
        return [_model(item) for item in store.list_milestones(project_id=project_id)]

    @app.get("/api/v1/milestones/{milestone_id}/deployment-pair")
    def deployment_pair(
        milestone_id: str,
        baseline_mode: str = Query(default="AUTO", pattern="^(AUTO|GOLDEN)$"),
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> dict[str, Any]:
        milestone = store.get_milestone(milestone_id)
        if milestone is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="milestone not found")
        require_project_read(store, principal, milestone.project_id)
        try:
            return _model(resolve_deployment_pair(store, milestone, baseline_mode=baseline_mode))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.get("/api/v1/organizations/{organization_id}/usage")
    def organization_usage(
        organization_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, Any]]:
        if organization_id not in accessible_organization_ids(store, principal):
            raise AuthorizationError("organization is outside the caller tenancy scope")
        return list(_safe(store.usage_summary(organization_id)))

    @app.get("/api/v1/audits/{audit_id}/reports")
    def audit_reports(
        audit_id: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> list[dict[str, str]]:
        audit = _authorized_audit(store, principal, audit_id)
        root = _report_root(audit)
        return [
            {
                "name": filename,
                "label": label,
                "url": f"/api/v1/audits/{audit.audit_id}/reports/{filename}",
            }
            for filename, label in _CANONICAL_REPORT_PAGES
            if (root / filename).is_file()
        ]

    @app.get("/api/v1/audits/{audit_id}/reports/{asset_path:path}", include_in_schema=False)
    def audit_report_asset(
        audit_id: str,
        asset_path: str,
        principal: Principal = Depends(principal_dependency),
        store: Any = Depends(store_dependency),
    ) -> FileResponse:
        audit = _authorized_audit(store, principal, audit_id)
        candidate = _report_asset(_report_root(audit), asset_path)
        return FileResponse(
            candidate,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

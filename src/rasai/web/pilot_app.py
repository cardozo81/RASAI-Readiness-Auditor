"""Composition root for the zero-build SaaS pilot browser surface.

The canonical API remains implemented in :mod:`rasai.web.app`. This module composes
additive browser/read-projection, identity, and SaaS management routes without
moving or duplicating API behavior.
"""
from __future__ import annotations

from typing import Any, Iterator

from fastapi import Request

from .app import ApiSettings, SearchRepositoryFactory, StoreFactory, create_app as create_api_app
from .auth import PrincipalResolver
from .authz import Principal
from .identity_routes import install_identity_routes
from .pilot import install_pilot_routes
from .saas_management_routes import install_saas_management_routes


def create_app(
    settings: ApiSettings | None = None,
    *,
    store_factory: StoreFactory | None = None,
    search_repository_factory: SearchRepositoryFactory | None = None,
    principal_resolver: PrincipalResolver | None = None,
) -> Any:
    app = create_api_app(
        settings,
        store_factory=store_factory,
        search_repository_factory=search_repository_factory,
        principal_resolver=principal_resolver,
    )

    def store_dependency(request: Request) -> Iterator[Any]:
        store = request.app.state.store_factory()
        try:
            yield store
        finally:
            store.close()

    async def principal_dependency(request: Request) -> Principal:
        return await request.app.state.principal_resolver(request)

    install_identity_routes(app, app.state.settings.auth)
    install_pilot_routes(
        app,
        store_dependency=store_dependency,
        principal_dependency=principal_dependency,
    )
    install_saas_management_routes(
        app,
        store_dependency=store_dependency,
        principal_dependency=principal_dependency,
    )
    return app


app = create_app()

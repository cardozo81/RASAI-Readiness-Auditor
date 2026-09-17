from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from rasai.platform.saas_store import SaaSSecurePlatformStore
from rasai.web.app import ApiSettings
from rasai.web.auth import ApiAuthSettings
from rasai.web.pilot_app import create_app


def _seed(database: Path):
    with SaaSSecurePlatformStore(database) as store:
        org_a = store.get_or_create_organization("Semantic Tenant A", slug="semantic-a")
        ws_a = store.get_or_create_workspace(org_a.organization_id, "A", slug="semantic-wa")
        project_a = store.get_or_create_project(ws_a.workspace_id, "A", slug="semantic-pa")
        prop_a = store.get_or_create_property(project_a.project_id, "A", "https://a.semantic.test")
        store.get_or_create_environment(prop_a.property_id, "Production", "PRODUCTION", prop_a.canonical_origin)

        org_b = store.get_or_create_organization("Semantic Tenant B", slug="semantic-b")
        ws_b = store.get_or_create_workspace(org_b.organization_id, "B", slug="semantic-wb")
        project_b = store.get_or_create_project(ws_b.workspace_id, "B", slug="semantic-pb")
        prop_b = store.get_or_create_property(project_b.project_id, "B", "https://b.semantic.test")
        store.get_or_create_environment(prop_b.property_id, "Production", "PRODUCTION", prop_b.canonical_origin)

        operator = store.get_or_create_user("Operator", email="semantic-operator@example.test")
        store.add_membership(org_a.organization_id, operator.user_id, "OPERATOR", workspace_id=ws_a.workspace_id, project_id=project_a.project_id)
        viewer = store.get_or_create_user("Viewer", email="semantic-viewer@example.test")
        store.add_membership(org_a.organization_id, viewer.user_id, "VIEWER", workspace_id=ws_a.workspace_id, project_id=project_a.project_id)
        outsider = store.get_or_create_user("Outsider", email="semantic-outsider@example.test")
        store.add_membership(org_b.organization_id, outsider.user_id, "OPERATOR", workspace_id=ws_b.workspace_id, project_id=project_b.project_id)
    return locals()


def _headers(user) -> dict[str, str]:
    return {"x-rasai-user-id": user.user_id}


def _app(database: Path):
    return create_app(
        ApiSettings(
            audits_root=database.parent,
            docs_enabled=False,
            auth=ApiAuthSettings(mode="trusted-header", trusted_user_header="x-rasai-user-id"),
        ),
        store_factory=lambda: SaaSSecurePlatformStore(database),
    )


def test_semantic_profile_api_is_tenant_safe_and_revisioned(tmp_path: Path) -> None:
    database = tmp_path / "platform.db"
    seed = _seed(database)
    url = f"/api/v1/properties/{seed['prop_a'].property_id}/semantic-profile"

    with TestClient(_app(database)) as client:
        initial = client.get(url, headers=_headers(seed["viewer"]))
        assert initial.status_code == 200
        assert initial.json()["revision"] == 0

        denied = client.put(url, headers=_headers(seed["viewer"]), json={"business_sector": "Software"})
        assert denied.status_code == 403

        cross_tenant = client.get(url, headers=_headers(seed["outsider"]))
        assert cross_tenant.status_code == 403

        saved = client.put(
            url,
            headers=_headers(seed["operator"]),
            json={
                "business_sector": "Software B2B",
                "business_description": "Plataforma financeira",
                "primary_offering": "SaaS financeiro",
                "target_audience_profile": "CFOs de PMEs",
                "primary_goal": "Gerar demonstrações",
                "positioning": "Simplificar finanças",
                "expected_revision": 0,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 1

        conflict = client.put(
            url,
            headers=_headers(seed["operator"]),
            json={"business_sector": "Outro", "expected_revision": 0},
        )
        assert conflict.status_code == 409

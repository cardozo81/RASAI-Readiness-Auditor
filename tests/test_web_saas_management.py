from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from rasai.m25_cli import DEFAULT_UX_FRUSTRATED_SECONDS, DEFAULT_UX_SATISFIED_SECONDS
from rasai.platform.saas_store import SaaSSecurePlatformStore
from rasai.web.app import ApiSettings
from rasai.web.auth import ApiAuthSettings
from rasai.web.pilot_app import create_app


def _seed(database: Path):
    with SaaSSecurePlatformStore(database) as store:
        org_a = store.get_or_create_organization("Tenant A", slug="saas-a")
        ws_a = store.get_or_create_workspace(org_a.organization_id, "Workspace A", slug="saas-ws-a")
        project_a = store.get_or_create_project(ws_a.workspace_id, "Project A", slug="saas-project-a")
        prop_a = store.get_or_create_property(project_a.project_id, "Site A", "https://a.example.test")
        env_a = store.get_or_create_environment(prop_a.property_id, "Production", "PRODUCTION", prop_a.canonical_origin)

        org_b = store.get_or_create_organization("Tenant B", slug="saas-b")
        ws_b = store.get_or_create_workspace(org_b.organization_id, "Workspace B", slug="saas-ws-b")
        project_b = store.get_or_create_project(ws_b.workspace_id, "Project B", slug="saas-project-b")
        prop_b = store.get_or_create_property(project_b.project_id, "Site B", "https://b.example.test")
        env_b = store.get_or_create_environment(prop_b.property_id, "Production", "PRODUCTION", prop_b.canonical_origin)

        operator = store.get_or_create_user("Operator A", email="saas-operator@example.test")
        store.add_membership(org_a.organization_id, operator.user_id, "OPERATOR", workspace_id=ws_a.workspace_id, project_id=project_a.project_id)
        viewer = store.get_or_create_user("Viewer A", email="saas-viewer@example.test")
        store.add_membership(org_a.organization_id, viewer.user_id, "VIEWER", workspace_id=ws_a.workspace_id, project_id=project_a.project_id)
        outsider = store.get_or_create_user("Operator B", email="saas-outsider@example.test")
        store.add_membership(org_b.organization_id, outsider.user_id, "OPERATOR", workspace_id=ws_b.workspace_id, project_id=project_b.project_id)

        store.record_usage_once(
            source_key="web-test:usage:1",
            organization_id=org_a.organization_id,
            project_id=project_a.project_id,
            property_id=prop_a.property_id,
            category="AI_PROVIDER_CALL",
            quantity=1,
            unit="call",
            provider="openai",
            cost_estimate=0.10,
            currency="USD",
            metadata={
                "environment_id": env_a.environment_id,
                "user_id": operator.user_id,
                "url": "https://a.example.test/a",
                "domain": "a.example.test",
                "operation": "SEMANTIC_ANALYSIS",
                "resource_type": "AI",
                "status": "SUCCESS",
                "total_tokens": 50,
            },
            occurred_at="2026-09-10T10:00:00-03:00",
        )
    return locals()


def _app(database: Path):
    return create_app(
        ApiSettings(
            audits_root=database.parent,
            docs_enabled=False,
            auth=ApiAuthSettings(mode="trusted-header", trusted_user_header="x-rasai-user-id"),
        ),
        store_factory=lambda: SaaSSecurePlatformStore(database),
    )


def _h(user) -> dict[str, str]:
    return {"x-rasai-user-id": user.user_id}


def _body(seed) -> dict:
    return {
        "property_id": seed["prop_a"].property_id,
        "environment_id": seed["env_a"].environment_id,
        "name": "Audit weekdays",
        "job_type": "AUDIT",
        "timezone": "America/Sao_Paulo",
        "overlap_policy": "SKIP",
        "urls": ["/a", "/b"],
        "payload": {"max_pages": 20, "device_context": "both", "ai_provider": "none"},
        "recurrence": {"times": ["08:00", "12:00", "18:00"], "weekdays": [1, 2, 3, 4, 5]},
    }


def test_schedule_api_crud_rbac_tenant_isolation_and_preview() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seed = _seed(database)
        with TestClient(_app(database)) as client:
            options = client.get("/api/v1/audit-job-options", headers=_h(seed["operator"]))
            assert options.status_code == 200, options.text
            defaults = options.json()["defaults"]
            assert defaults["apdex_experience_satisfied_seconds"] == DEFAULT_UX_SATISFIED_SECONDS
            assert defaults["apdex_experience_frustrated_seconds"] == DEFAULT_UX_FRUSTRATED_SECONDS
            assert "lighthouse_categories" in defaults
            assert "ai_provider" in defaults

            created = client.post(
                f"/api/v1/projects/{seed['project_a'].project_id}/schedules",
                headers=_h(seed["operator"]),
                json=_body(seed),
            )
            assert created.status_code == 201, created.text
            schedule = created.json()
            assert schedule["urls"] == ["https://a.example.test/a", "https://a.example.test/b"]
            schedule_id = schedule["schedule_id"]

            invalid_payload = client.post(
                f"/api/v1/projects/{seed['project_a'].project_id}/schedules",
                headers=_h(seed["operator"]),
                json={**_body(seed), "name": "Invalid payload", "payload": {"unsupported_runtime_option": True}},
            )
            assert invalid_payload.status_code == 422

            listed = client.get(
                f"/api/v1/projects/{seed['project_a'].project_id}/schedules",
                headers=_h(seed["operator"]),
            )
            assert listed.status_code == 200
            assert [item["schedule_id"] for item in listed.json()] == [schedule_id]

            preview = client.get(
                f"/api/v1/schedules/{schedule_id}/next-occurrences?count=3",
                headers=_h(seed["viewer"]),
            )
            assert preview.status_code == 200
            assert len(preview.json()["occurrences"]) == 3

            denied_viewer = client.post(
                f"/api/v1/projects/{seed['project_a'].project_id}/schedules",
                headers=_h(seed["viewer"]),
                json={**_body(seed), "name": "Viewer cannot persist"},
            )
            assert denied_viewer.status_code == 403

            cross_tenant = client.get(
                f"/api/v1/schedules/{schedule_id}", headers=_h(seed["outsider"])
            )
            assert cross_tenant.status_code == 403

            external = client.post(
                f"/api/v1/projects/{seed['project_a'].project_id}/schedules",
                headers=_h(seed["operator"]),
                json={**_body(seed), "name": "Bad URL", "urls": ["https://b.example.test/escape"]},
            )
            assert external.status_code == 422

            patched = client.patch(
                f"/api/v1/schedules/{schedule_id}",
                headers=_h(seed["operator"]),
                json={"recurrence": {"times": ["07:00"], "month_days": [1, 15], "last_day": True}},
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["recurrence"]["month_days"] == [1, 15]

            bad_patch = client.patch(
                f"/api/v1/schedules/{schedule_id}",
                headers=_h(seed["operator"]),
                json={"payload": {"synthetic_apdex": True}},
            )
            assert bad_patch.status_code == 422

            paused = client.post(f"/api/v1/schedules/{schedule_id}/pause", headers=_h(seed["operator"]))
            assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
            resumed = client.post(f"/api/v1/schedules/{schedule_id}/resume", headers=_h(seed["operator"]))
            assert resumed.status_code == 200 and resumed.json()["status"] == "ACTIVE"
            copied = client.post(
                f"/api/v1/schedules/{schedule_id}/duplicate",
                headers=_h(seed["operator"]),
                json={"name": "Audit weekdays copy"},
            )
            assert copied.status_code == 201, copied.text
            disabled = client.delete(f"/api/v1/schedules/{schedule_id}", headers=_h(seed["operator"]))
            assert disabled.status_code == 200 and disabled.json()["status"] == "DISABLED"

            operations = client.get("/app/operations")
            assert operations.status_code == 200
            assert "Scheduling Management" in operations.text
            assert "Consumption Analytics" in operations.text
            assert "Configuração AUDIT canônica" in operations.text
            assert "/api/v1/audit-job-options" in operations.text

            pilot = client.get("/app")
            assert pilot.status_code == 200
            assert 'id="audit-config"' in pilot.text
            assert "/api/v1/audit-job-options" in pilot.text


def test_consumption_api_filters_groups_and_never_invents_missing_cost() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seed = _seed(database)
        with TestClient(_app(database)) as client:
            response = client.get(
                f"/api/v1/organizations/{seed['org_a'].organization_id}/consumption",
                headers=_h(seed["operator"]),
                params={
                    "workspace_id": seed["ws_a"].workspace_id,
                    "project_id": seed["project_a"].project_id,
                    "property_id": seed["prop_a"].property_id,
                    "environment_id": seed["env_a"].environment_id,
                    "domain": "a.example.test",
                    "user_id": seed["operator"].user_id,
                    "start": "2026-09-10T00:00:00-03:00",
                    "end": "2026-09-11T00:00:00-03:00",
                    "group_by": "property,url,user,provider,category",
                },
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["summary"]["event_count"] == 1
            assert data["summary"]["cost_by_currency"] == {"USD": 0.10}
            assert data["summary"]["total_tokens"] == 50
            assert data["coverage"]["with_url"] == 1
            assert data["coverage"]["with_workspace"] == 1

            period = client.get(
                f"/api/v1/organizations/{seed['org_a'].organization_id}/consumption",
                headers=_h(seed["operator"]),
                params={"period": "LAST_30_DAYS", "timezone": "America/Sao_Paulo"},
            )
            assert period.status_code == 200, period.text

            invalid_period = client.get(
                f"/api/v1/organizations/{seed['org_a'].organization_id}/consumption",
                headers=_h(seed["operator"]),
                params={"period": "TODAY", "start": "2026-09-10T00:00:00-03:00"},
            )
            assert invalid_period.status_code == 422

            foreign = client.get(
                f"/api/v1/organizations/{seed['org_a'].organization_id}/consumption",
                headers=_h(seed["outsider"]),
            )
            assert foreign.status_code == 403

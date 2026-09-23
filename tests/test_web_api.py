from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from rasai.platform.models import AuditIndexRecord
from rasai.platform.secure_store import SecurePlatformStore
from rasai.search_intelligence.monitoring import new_query
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository
from rasai.web.app import ApiSettings, create_app
from rasai.web.auth import ApiAuthSettings


def _seed(database: Path):
    with SecurePlatformStore(database) as store:
        org_a = store.get_or_create_organization("Tenant A", slug="tenant-a")
        ws_a = store.get_or_create_workspace(org_a.organization_id, "Workspace A", slug="workspace-a")
        project_a = store.get_or_create_project(ws_a.workspace_id, "Project A", slug="project-a")
        prop_a = store.get_or_create_property(project_a.project_id, "Site A", "https://a.example.test")
        env_a = store.get_or_create_environment(
            prop_a.property_id, "Production", "PRODUCTION", prop_a.canonical_origin
        )

        org_b = store.get_or_create_organization("Tenant B", slug="tenant-b")
        ws_b = store.get_or_create_workspace(org_b.organization_id, "Workspace B", slug="workspace-b")
        project_b = store.get_or_create_project(ws_b.workspace_id, "Project B", slug="project-b")
        prop_b = store.get_or_create_property(project_b.project_id, "Site B", "https://b.example.test")
        env_b = store.get_or_create_environment(
            prop_b.property_id, "Production", "PRODUCTION", prop_b.canonical_origin
        )

        operator = store.get_or_create_user("Operator A", email="operator-a@example.test")
        store.add_membership(
            org_a.organization_id,
            operator.user_id,
            "OPERATOR",
            workspace_id=ws_a.workspace_id,
            project_id=project_a.project_id,
        )
        viewer = store.get_or_create_user("Viewer A", email="viewer-a@example.test")
        store.add_membership(
            org_a.organization_id,
            viewer.user_id,
            "VIEWER",
            workspace_id=ws_a.workspace_id,
            project_id=project_a.project_id,
        )
        outsider = store.get_or_create_user("Operator B", email="operator-b@example.test")
        store.add_membership(
            org_b.organization_id,
            outsider.user_id,
            "OPERATOR",
            workspace_id=ws_b.workspace_id,
            project_id=project_b.project_id,
        )

    with open_search_monitoring_repository(platform_db=database) as repository:
        query_a = repository.register_query(
            new_query(
                project_id=project_a.project_id,
                property_id=prop_a.property_id,
                environment_id=env_a.environment_id,
                query="rasai readiness",
                domain_of_interest="a.example.test",
                mode="disabled",
                provider="serpapi",
            )
        )
        query_b = repository.register_query(
            new_query(
                project_id=project_b.project_id,
                property_id=prop_b.property_id,
                environment_id=env_b.environment_id,
                query="other tenant",
                domain_of_interest="b.example.test",
                mode="disabled",
                provider="serpapi",
            )
        )
    return {
        "org_a": org_a,
        "ws_a": ws_a,
        "project_a": project_a,
        "prop_a": prop_a,
        "env_a": env_a,
        "org_b": org_b,
        "project_b": project_b,
        "prop_b": prop_b,
        "env_b": env_b,
        "operator": operator,
        "viewer": viewer,
        "outsider": outsider,
        "query_a": query_a,
        "query_b": query_b,
    }


def _app(database: Path, *, auth_mode: str = "trusted-header"):
    settings = ApiSettings(
        audits_root=database.parent,
        docs_enabled=False,
        auth=ApiAuthSettings(mode=auth_mode, trusted_user_header="x-rasai-user-id"),
    )
    return create_app(
        settings,
        store_factory=lambda: SecurePlatformStore(database),
        search_repository_factory=lambda: open_search_monitoring_repository(platform_db=database),
    )


def _headers(user_id: str) -> dict[str, str]:
    return {"x-rasai-user-id": user_id}


def _index_consolidation_audits(database: Path, seeded: dict) -> None:
    with SecurePlatformStore(database) as store:
        for prefix, prop, env, domain in (
            ("A", seeded["prop_a"], seeded["env_a"], "a.example.test"),
            ("B", seeded["prop_b"], seeded["env_b"], "b.example.test"),
        ):
            for pos, when in ((1, "2026-08-01T10:00:00+00:00"), (2, "2026-09-01T10:00:00+00:00")):
                store.upsert_audit(
                    AuditIndexRecord(
                        audit_id=f"AUD-{prefix}-{pos:03d}",
                        property_id=prop.property_id,
                        environment_id=env.environment_id,
                        workspace_path=str(database.parent / f"AUD-{prefix}-{pos:03d}"),
                        audit_db_sha256=f"sha-{prefix}-{pos}",
                        event_time=when,
                        status="COMPLETED",
                        completion_status="COMPLETE",
                        project_name=f"Project {prefix}",
                        auditor_version="test",
                        ruleset_version="test",
                        scoring_versions=("SCORE-GEO-004",),
                        domains=(domain,),
                        devices=("MOBILE",),
                        url_count=1,
                        indexed_at=when,
                    )
                )


def test_api_defaults_to_fail_closed_authentication() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seeded = _seed(database)
        with TestClient(_app(database, auth_mode="deny")) as client:
            assert client.get("/health/live").status_code == 200
            response = client.get("/api/v1/me", headers=_headers(seeded["operator"].user_id))
            assert response.status_code == 503


def test_api_filters_tenants_and_exposes_search_registry_without_cross_tenant_leakage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seeded = _seed(database)
        headers = _headers(seeded["operator"].user_id)
        with TestClient(_app(database)) as client:
            ready = client.get("/health/ready")
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"

            me = client.get("/api/v1/me", headers=headers)
            assert me.status_code == 200
            assert me.json()["project_ids"] == [seeded["project_a"].project_id]

            organizations = client.get("/api/v1/organizations", headers=headers)
            assert [item["organization_id"] for item in organizations.json()] == [seeded["org_a"].organization_id]

            projects = client.get(
                f"/api/v1/workspaces/{seeded['ws_a'].workspace_id}/projects", headers=headers
            )
            assert [item["project_id"] for item in projects.json()] == [seeded["project_a"].project_id]

            denied = client.get(
                f"/api/v1/projects/{seeded['project_b'].project_id}/properties", headers=headers
            )
            assert denied.status_code == 403

            queries = client.get(
                f"/api/v1/projects/{seeded['project_a'].project_id}/search-queries", headers=headers
            )
            assert queries.status_code == 200
            assert [item["query_id"] for item in queries.json()] == [seeded["query_a"].query_id]
            assert seeded["query_b"].query_id not in queries.text

            foreign_runs = client.get(
                f"/api/v1/search-queries/{seeded['query_b'].query_id}/runs", headers=headers
            )
            assert foreign_runs.status_code == 403


def test_execution_api_is_idempotent_role_scoped_and_secret_safe() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seeded = _seed(database)
        operator_headers = _headers(seeded["operator"].user_id)
        viewer_headers = _headers(seeded["viewer"].user_id)
        payload = {
            "property_id": seeded["prop_a"].property_id,
            "environment_id": seeded["env_a"].environment_id,
            "job_type": "SEARCH_MONITOR",
            "payload": {"query_id": seeded["query_a"].query_id},
            "idempotency_key": "api-monitor-1",
        }
        with TestClient(_app(database)) as client:
            created = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/execution-jobs",
                headers=operator_headers,
                json=payload,
            )
            assert created.status_code == 202
            job_id = created.json()["job_id"]
            repeated = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/execution-jobs",
                headers=operator_headers,
                json=payload,
            )
            assert repeated.status_code == 202
            assert repeated.json()["job_id"] == job_id

            viewer_create = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/execution-jobs",
                headers=viewer_headers,
                json={**payload, "idempotency_key": "viewer-denied"},
            )
            assert viewer_create.status_code == 403

            secret_marker = "TEST_ONLY_NOT_A_REAL_SECRET"
            unsafe = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/execution-jobs",
                headers=operator_headers,
                json={
                    **payload,
                    "idempotency_key": "unsafe",
                    "payload": {"api_key": secret_marker},
                },
            )
            assert unsafe.status_code == 422
            assert secret_marker not in unsafe.text

            listed = client.get(
                f"/api/v1/projects/{seeded['project_a'].project_id}/execution-jobs",
                headers=operator_headers,
            )
            assert listed.status_code == 200
            assert [item["job_id"] for item in listed.json()] == [job_id]

            cancelled = client.post(
                f"/api/v1/execution-jobs/{job_id}/cancel", headers=operator_headers
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "CANCELLED"


def test_consolidated_report_api_enqueues_tenant_scoped_report_refresh() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        seeded = _seed(database)
        _index_consolidation_audits(database, seeded)
        operator_headers = _headers(seeded["operator"].user_id)
        viewer_headers = _headers(seeded["viewer"].user_id)
        payload = {
            "property_id": seeded["prop_a"].property_id,
            "environment_id": seeded["env_a"].environment_id,
            "baseline_audit_id": "AUD-A-001",
            "current_audit_id": "AUD-A-002",
            "selection_mode": "ALL",
            "use_ai": False,
            "idempotency_key": "consolidated-1",
        }
        with TestClient(_app(database)) as client:
            created = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/consolidated-reports",
                headers=operator_headers,
                json=payload,
            )
            assert created.status_code == 202
            body = created.json()
            assert body["report_kind"] == "Relatório consolidado longitudinal"
            assert body["selection_request"]["baseline_audit_id"] == "AUD-A-001"
            assert body["selection_request"]["current_audit_id"] == "AUD-A-002"
            assert body["selection_request"]["selection_mode"] == "ALL"
            assert body["selection_request"]["use_ai"] is False
            job_id = body["job_id"]

            report = Path(directory) / "consolidated" / "CONS-TEST" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html><body>CONS-TEST</body></html>", encoding="utf-8")
            with SecurePlatformStore(database) as store:
                claimed = store.claim_execution_job("worker-cons")
                assert claimed is not None and claimed.job_id == job_id
                running = store.start_execution_job(job_id, "worker-cons")
                store.finish_execution_job(
                    running.job_id,
                    "worker-cons",
                    succeeded=True,
                    result_ref="consolidated/CONS-TEST/report.html",
                    result_metadata={"surface": "consolidated"},
                )

            result = client.get(
                f"/api/v1/execution-jobs/{job_id}/result",
                headers=operator_headers,
            )
            assert result.status_code == 200
            assert "CONS-TEST" in result.text
            assert result.headers["cache-control"] == "no-store"

            viewer = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/consolidated-reports",
                headers=viewer_headers,
                json={**payload, "idempotency_key": "viewer-consolidated"},
            )
            assert viewer.status_code == 403

            foreign = client.post(
                f"/api/v1/projects/{seeded['project_b'].project_id}/consolidated-reports",
                headers=operator_headers,
                json={
                    **payload,
                    "property_id": seeded["prop_b"].property_id,
                    "environment_id": seeded["env_b"].environment_id,
                    "baseline_audit_id": "AUD-B-001",
                    "current_audit_id": "AUD-B-002",
                    "idempotency_key": "foreign-consolidated",
                },
            )
            assert foreign.status_code == 403

            ai_missing_provider = client.post(
                f"/api/v1/projects/{seeded['project_a'].project_id}/consolidated-reports",
                headers=operator_headers,
                json={**payload, "use_ai": True, "idempotency_key": "ai-without-provider"},
            )
            assert ai_missing_provider.status_code == 202
            queued = ai_missing_provider.json()
            assert queued["selection_request"]["use_ai"] is True




def test_ready_error_detail_redacts_database_credentials() -> None:
    class BrokenStore:
        def __enter__(self):
            raise RuntimeError("postgresql://rasai:TEST_ONLY_NOT_A_REAL_SECRET@db.example.test/control")

        def __exit__(self, *_args):
            return None

    settings = ApiSettings(auth=ApiAuthSettings(mode="deny"))
    app = create_app(settings, store_factory=BrokenStore)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "TEST_ONLY_NOT_A_REAL_SECRET" not in response.text
        assert "db.example.test" in response.text

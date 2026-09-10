from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from rasai.platform.models import AuditIndexRecord
from rasai.platform.secure_store import SecurePlatformStore
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository
from rasai.web.app import ApiSettings
from rasai.web.auth import ApiAuthSettings
from rasai.web.pilot_app import create_app


def _seed(database: Path, root: Path) -> dict[str, object]:
    with SecurePlatformStore(database) as store:
        org_a = store.get_or_create_organization("Tenant A", slug="tenant-a")
        ws_a = store.get_or_create_workspace(org_a.organization_id, "Workspace A", slug="workspace-a")
        project_a = store.get_or_create_project(ws_a.workspace_id, "Project A", slug="project-a")
        prop_a = store.get_or_create_property(project_a.project_id, "Site A", "https://a.example.test")
        env_a = store.get_or_create_environment(prop_a.property_id, "Production", "PRODUCTION", prop_a.canonical_origin)

        org_b = store.get_or_create_organization("Tenant B", slug="tenant-b")
        ws_b = store.get_or_create_workspace(org_b.organization_id, "Workspace B", slug="workspace-b")
        project_b = store.get_or_create_project(ws_b.workspace_id, "Project B", slug="project-b")
        prop_b = store.get_or_create_property(project_b.project_id, "Site B", "https://b.example.test")
        env_b = store.get_or_create_environment(prop_b.property_id, "Production", "PRODUCTION", prop_b.canonical_origin)

        user_a = store.get_or_create_user("Operator A", email="operator-a@example.test")
        store.add_membership(
            org_a.organization_id,
            user_a.user_id,
            "OPERATOR",
            workspace_id=ws_a.workspace_id,
            project_id=project_a.project_id,
        )
        user_b = store.get_or_create_user("Operator B", email="operator-b@example.test")
        store.add_membership(
            org_b.organization_id,
            user_b.user_id,
            "OPERATOR",
            workspace_id=ws_b.workspace_id,
            project_id=project_b.project_id,
        )

        milestone_a = store.add_milestone(
            project_id=project_a.project_id,
            property_id=prop_a.property_id,
            environment_id=env_a.environment_id,
            kind="DEPLOYMENT",
            occurred_at="2026-09-09T10:00:00-03:00",
            title="Release A",
        )
        store.add_milestone(
            project_id=project_b.project_id,
            property_id=prop_b.property_id,
            environment_id=env_b.environment_id,
            kind="DEPLOYMENT",
            occurred_at="2026-09-09T10:00:00-03:00",
            title="Release B",
        )

        workspace = root / "AUD-WEB-PILOT"
        report = workspace / "report"
        (report / "css").mkdir(parents=True)
        (report / "index.html").write_text(
            '<!doctype html><html><head><link rel="stylesheet" href="css/site.css"></head><body>Tenant A report</body></html>',
            encoding="utf-8",
        )
        (report / "css" / "site.css").write_text("body{font-family:sans-serif}", encoding="utf-8")
        (workspace / "audit.db").write_bytes(b"private audit database bytes")
        audit = AuditIndexRecord(
            audit_id="AUD-WEB-PILOT",
            property_id=prop_a.property_id,
            environment_id=env_a.environment_id,
            workspace_path=str(workspace),
            audit_db_sha256="0" * 64,
            event_time="2026-09-09T11:00:00-03:00",
            status="COMPLETED",
            completion_status="SUCCESS",
            project_name=project_a.name,
            auditor_version="test",
            ruleset_version="test",
            scoring_versions=("SCORE-GEO-004",),
            domains=("a.example.test",),
            devices=("mobile", "desktop"),
            url_count=1,
            indexed_at="2026-09-09T11:01:00-03:00",
        )
        store.upsert_audit(audit)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "project_a": project_a,
        "project_b": project_b,
        "user_a": user_a,
        "user_b": user_b,
        "milestone_a": milestone_a,
        "audit": audit,
    }


def _app(database: Path):
    settings = ApiSettings(
        audits_root=database.parent,
        docs_enabled=False,
        auth=ApiAuthSettings(mode="trusted-header", trusted_user_header="x-rasai-user-id"),
    )
    return create_app(
        settings,
        store_factory=lambda: SecurePlatformStore(database),
        search_repository_factory=lambda: open_search_monitoring_repository(platform_db=database),
    )


def _headers(user_id: str) -> dict[str, str]:
    return {"x-rasai-user-id": user_id}


def test_pilot_shell_is_zero_build_and_contains_no_tenant_data() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "platform.db"
        _seed(database, root)
        with TestClient(_app(database)) as client:
            response = client.get("/app")
            assert response.status_code == 200
            assert "SaaS Pilot" in response.text
            assert "Tenant A report" not in response.text
            assert "default-src 'self'" in response.headers["content-security-policy"]
            assert "cdn." not in response.text


def test_pilot_projections_preserve_tenant_scope() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "platform.db"
        seeded = _seed(database, root)
        headers = _headers(seeded["user_a"].user_id)
        with TestClient(_app(database)) as client:
            milestones = client.get(
                f"/api/v1/projects/{seeded['project_a'].project_id}/milestones",
                headers=headers,
            )
            assert milestones.status_code == 200
            assert [item["title"] for item in milestones.json()] == ["Release A"]

            denied_project = client.get(
                f"/api/v1/projects/{seeded['project_b'].project_id}/milestones",
                headers=headers,
            )
            assert denied_project.status_code == 403

            usage = client.get(
                f"/api/v1/organizations/{seeded['org_a'].organization_id}/usage",
                headers=headers,
            )
            assert usage.status_code == 200
            assert usage.json() == []

            denied_usage = client.get(
                f"/api/v1/organizations/{seeded['org_b'].organization_id}/usage",
                headers=headers,
            )
            assert denied_usage.status_code == 403

            pair = client.get(
                f"/api/v1/milestones/{seeded['milestone_a'].milestone_id}/deployment-pair",
                headers=headers,
            )
            assert pair.status_code == 200
            assert pair.json()["baseline_audit_id"] is None
            assert pair.json()["current_audit_id"] == seeded["audit"].audit_id


def test_report_boundary_serves_only_authorized_public_report_tree() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "platform.db"
        seeded = _seed(database, root)
        headers = _headers(seeded["user_a"].user_id)
        outsider_headers = _headers(seeded["user_b"].user_id)
        audit_id = seeded["audit"].audit_id
        with TestClient(_app(database)) as client:
            listed = client.get(f"/api/v1/audits/{audit_id}/reports", headers=headers)
            assert listed.status_code == 200
            assert listed.json() == [{
                "name": "index.html",
                "label": "Visão geral",
                "url": f"/api/v1/audits/{audit_id}/reports/index.html",
            }]
            assert "workspace_path" not in listed.text

            report = client.get(f"/api/v1/audits/{audit_id}/reports/index.html", headers=headers)
            assert report.status_code == 200
            assert "Tenant A report" in report.text

            css = client.get(f"/api/v1/audits/{audit_id}/reports/css/site.css", headers=headers)
            assert css.status_code == 200

            private_db = client.get(f"/api/v1/audits/{audit_id}/reports/%2e%2e/audit.db", headers=headers)
            assert private_db.status_code == 404
            assert b"private audit database bytes" not in private_db.content

            outsider = client.get(f"/api/v1/audits/{audit_id}/reports/index.html", headers=outsider_headers)
            assert outsider.status_code == 403

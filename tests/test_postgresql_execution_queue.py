from __future__ import annotations

import os
from uuid import uuid4

import pytest

from rasai.platform.postgres_admin import migrate_postgres, postgres_schema_status
from rasai.platform.postgres_execution_migration import EXECUTION_SCHEMA_VERSION
from rasai.platform.postgres_store import PostgreSQLPlatformStore


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    if POSTGRES_URL:
        status, _applied = migrate_postgres(POSTGRES_URL)
        assert status.state == "CURRENT"
        assert status.execution_current_version == EXECUTION_SCHEMA_VERSION


def test_postgresql_execution_schema_is_explicit_and_current() -> None:
    assert POSTGRES_URL is not None
    status = postgres_schema_status(POSTGRES_URL)
    assert status.state == "CURRENT"
    assert status.execution_current_version == EXECUTION_SCHEMA_VERSION
    assert status.execution_supported_version == EXECUTION_SCHEMA_VERSION


def test_postgresql_execution_queue_parity() -> None:
    assert POSTGRES_URL is not None
    suffix = uuid4().hex[:10]
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        organization = store.get_or_create_organization(f"Queue Org {suffix}", slug=f"queue-org-{suffix}")
        workspace = store.get_or_create_workspace(
            organization.organization_id, f"Queue Workspace {suffix}", slug=f"queue-ws-{suffix}"
        )
        project = store.get_or_create_project(
            workspace.workspace_id, f"Queue Project {suffix}", slug=f"queue-project-{suffix}"
        )
        prop = store.get_or_create_property(
            project.project_id, f"Queue Site {suffix}", f"https://{suffix}.queue.example.test"
        )
        environment = store.get_or_create_environment(
            prop.property_id, "Production", "PRODUCTION", prop.canonical_origin
        )
        user = store.get_or_create_user(
            f"Queue Operator {suffix}", email=f"queue-{suffix}@example.test"
        )
        store.add_membership(
            organization.organization_id,
            user.user_id,
            "OPERATOR",
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
        )

        first = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="REPORT_REFRESH",
            payload={"surface": "portfolio"},
            requested_by=user.user_id,
            idempotency_key=f"report-{suffix}",
        )
        repeated = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="REPORT_REFRESH",
            payload={"surface": "portfolio"},
            requested_by=user.user_id,
            idempotency_key=f"report-{suffix}",
        )
        assert first.job_id == repeated.job_id

        claimed = store.claim_execution_job(f"worker-{suffix}", job_types=("REPORT_REFRESH",))
        assert claimed is not None
        assert claimed.job_id == first.job_id
        assert claimed.status == "CLAIMED"
        assert claimed.attempts == 1

        running = store.start_execution_job(claimed.job_id, f"worker-{suffix}")
        assert running.status == "RUNNING"
        finished = store.finish_execution_job(
            running.job_id,
            f"worker-{suffix}",
            succeeded=True,
            result_ref=f"platform-report/{suffix}.html",
            result_metadata={"kind": "portfolio"},
        )
        assert finished.status == "SUCCEEDED"
        assert finished.result_metadata == {"kind": "portfolio"}

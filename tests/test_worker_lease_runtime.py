"""Lease renewal invariants for long-running governed SaaS audits."""
from __future__ import annotations

from datetime import datetime

import pytest

from rasai.platform.secure_store import SecurePlatformStore
from rasai.worker_lease_runtime import _install_store_renewal


def _scope(store: SecurePlatformStore):
    organization, workspace, project, prop, environment = store.ensure_local_hierarchy(
        project_name="Lease renewal",
        origin="https://lease.example.test",
    )
    user = store.get_or_create_user("Operator", email="lease-operator@example.test")
    store.add_membership(
        organization.organization_id,
        user.user_id,
        "OPERATOR",
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
    )
    return project, prop, environment, user


def test_active_worker_can_extend_its_execution_lease(tmp_path) -> None:
    _install_store_renewal()
    database = tmp_path / "platform.db"
    with SecurePlatformStore(database) as store:
        project, prop, environment, user = _scope(store)
        queued = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="AUDIT",
            payload={"ai_provider": "none"},
            requested_by=user.user_id,
        )
        claimed = store.claim_execution_job("worker-a", lease_seconds=30)
        assert claimed is not None and claimed.job_id == queued.job_id
        running = store.start_execution_job(claimed.job_id, "worker-a")
        assert running.lease_until is not None
        prior = datetime.fromisoformat(running.lease_until.replace("Z", "+00:00"))

        renewed = store.renew_execution_job_lease(
            running.job_id,
            "worker-a",
            lease_seconds=120,
        )
        assert renewed.lease_until is not None
        extended = datetime.fromisoformat(renewed.lease_until.replace("Z", "+00:00"))
        assert extended > prior
        assert renewed.claimed_by == "worker-a"
        assert renewed.status == "RUNNING"


def test_lease_renewal_rejects_wrong_worker_or_terminal_job(tmp_path) -> None:
    _install_store_renewal()
    database = tmp_path / "platform.db"
    with SecurePlatformStore(database) as store:
        project, prop, environment, user = _scope(store)
        queued = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="AUDIT",
            payload={"ai_provider": "none"},
            requested_by=user.user_id,
        )
        claimed = store.claim_execution_job("worker-a", lease_seconds=30)
        assert claimed is not None and claimed.job_id == queued.job_id

        with pytest.raises(ValueError, match="not active for this worker"):
            store.renew_execution_job_lease(claimed.job_id, "worker-b", lease_seconds=60)

        running = store.start_execution_job(claimed.job_id, "worker-a")
        store.finish_execution_job(running.job_id, "worker-a", succeeded=True)
        with pytest.raises(ValueError, match="not active for this worker"):
            store.renew_execution_job_lease(running.job_id, "worker-a", lease_seconds=60)


def test_lease_renewal_validates_bounds(tmp_path) -> None:
    _install_store_renewal()
    database = tmp_path / "platform.db"
    with SecurePlatformStore(database) as store:
        with pytest.raises(ValueError, match="between 30 and 86400"):
            store.renew_execution_job_lease("JOB-UNKNOWN", "worker-a", lease_seconds=29)
        with pytest.raises(ValueError, match="between 30 and 86400"):
            store.renew_execution_job_lease("JOB-UNKNOWN", "worker-a", lease_seconds=86401)

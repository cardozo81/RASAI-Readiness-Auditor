from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from rasai.platform.secure_store import SecurePlatformStore


def _scope(store: SecurePlatformStore):
    organization, workspace, project, prop, environment = store.ensure_local_hierarchy(
        project_name="Execution queue",
        origin="https://queue.example.test",
    )
    user = store.get_or_create_user("Operator", email="operator@example.test")
    store.add_membership(
        organization.organization_id,
        user.user_id,
        "OPERATOR",
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
    )
    return organization, workspace, project, prop, environment, user


def test_execution_queue_is_idempotent_secret_safe_and_worker_claimable() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        with SecurePlatformStore(database) as store:
            _organization, _workspace, project, prop, environment, user = _scope(store)
            first = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="SEARCH_MONITOR",
                payload={"query_id": "SQRY-EXAMPLE"},
                requested_by=user.user_id,
                idempotency_key="monitor-1",
            )
            second = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="SEARCH_MONITOR",
                payload={"query_id": "SQRY-EXAMPLE"},
                requested_by=user.user_id,
                idempotency_key="monitor-1",
            )
            assert first.job_id == second.job_id
            assert first.status == "QUEUED"
            assert first.payload == {"query_id": "SQRY-EXAMPLE"}

            with pytest.raises(ValueError):
                store.enqueue_execution_job(
                    project_id=project.project_id,
                    property_id=prop.property_id,
                    environment_id=environment.environment_id,
                    job_type="AUDIT",
                    payload={"api_key": "TEST_ONLY_NOT_A_REAL_SECRET"},
                    requested_by=user.user_id,
                )

            claimed = store.claim_execution_job("worker-a", job_types=("SEARCH_MONITOR",))
            assert claimed is not None
            assert claimed.job_id == first.job_id
            assert claimed.status == "CLAIMED"
            assert claimed.claimed_by == "worker-a"
            assert claimed.attempts == 1

            running = store.start_execution_job(claimed.job_id, "worker-a")
            assert running.status == "RUNNING"
            completed = store.finish_execution_job(
                running.job_id,
                "worker-a",
                succeeded=True,
                result_ref="search-monitoring/runs/example.json",
                result_metadata={"observation_id": "OBS-1"},
            )
            assert completed.status == "SUCCEEDED"
            assert completed.result_metadata == {"observation_id": "OBS-1"}
            assert store.claim_execution_job("worker-b") is None


def test_execution_queue_cancel_only_applies_before_running() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "platform.db"
        with SecurePlatformStore(database) as store:
            _organization, _workspace, project, prop, environment, user = _scope(store)
            item = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="REPORT_REFRESH",
                requested_by=user.user_id,
            )
            cancelled = store.cancel_execution_job(item.job_id)
            assert cancelled.status == "CANCELLED"
            with pytest.raises(ValueError):
                store.cancel_execution_job(item.job_id)

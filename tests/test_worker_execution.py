from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from rasai.platform.secure_store import SecurePlatformStore
from rasai.worker import _audit_arguments, execute_job
from rasai.worker_cli import main as worker_main


def _scope(store: SecurePlatformStore):
    organization, workspace, project, prop, environment = store.ensure_local_hierarchy(
        project_name="Worker",
        origin="https://worker.example.test",
    )
    user = store.get_or_create_user("Operator", email="worker@example.test")
    store.add_membership(
        organization.organization_id,
        user.user_id,
        "OPERATOR",
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
    )
    return project, prop, environment, user


def test_audit_job_builds_only_canonical_arguments() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with SecurePlatformStore(Path(directory) / "platform.db") as store:
            project, prop, environment, user = _scope(store)
            job = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="AUDIT",
                requested_by=user.user_id,
                payload={
                    "language": "pt-BR",
                    "market": "BR",
                    "max_pages": 25,
                    "device_context": "mobile",
                    "ai_provider": "none",
                    "web_performance": False,
                    "ai_content_remediation": False,
                },
            )
            argv = _audit_arguments(store, job, Path(directory) / "audits")
            assert argv[0:2] == ["audit", "https://worker.example.test"]
            assert "--max-pages" in argv and "25" in argv
            assert "--device-context" in argv and "mobile" in argv
            assert "--no-web-performance" in argv
            assert "--no-ai-content-remediation" in argv
            assert not any(value in {"cmd", "powershell", "bash", "sh"} for value in argv)

            invalid = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="AUDIT",
                requested_by=user.user_id,
                payload={"language": "pt-BR", "argv": ["--unsafe"]},
            )
            with pytest.raises(ValueError, match="unsupported AUDIT execution payload"):
                _audit_arguments(store, invalid, Path(directory) / "audits")


def test_report_refresh_job_executes_outside_http_process() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with SecurePlatformStore(root / "platform.db") as store:
            project, prop, environment, user = _scope(store)
            job = store.enqueue_execution_job(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                job_type="REPORT_REFRESH",
                requested_by=user.user_id,
                payload={"surface": "portfolio"},
            )
            result = execute_job(store, job, audits_root=root / "audits")
            assert result.result_ref is not None
            assert Path(result.result_ref).is_file()
            assert result.metadata == {"surface": "portfolio"}


def test_worker_cli_reports_idle_without_web_dependencies(capsys: pytest.CaptureFixture[str]) -> None:
    with tempfile.TemporaryDirectory() as directory:
        code = worker_main(["run-once", "--worker-id", "test-worker", "--audits-root", directory])
        assert code == 0
        assert '"status": "IDLE"' in capsys.readouterr().out

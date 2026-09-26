from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from rasai.audit_fulfillment import (
    SUCCESS,
    finish_reprocess_run,
    initialize_contract,
    read_summary,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.audit_fulfillment_saas import (
    _install_platform_revision_gate,
    _install_web_projection,
    _install_worker_reprocess,
)
from rasai.domain import Audit, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.platform.models import AuditIndexRecord
from rasai.platform.secure_store import SecurePlatformStore
from rasai.platform.store import file_sha256, utc_now


def _workspace(root: Path, audit_id: str = "AUD-SAAS-REPROCESS") -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="SaaS reprocess"))
        persistence.audits.complete(audit_id, CompletionStatus.COMPLETE)
    initialize_contract(workspace, audit_id, {"semantic_ai_requested": True})
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        required=True,
        status=SUCCESS,
        retryable=False,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{audit_id}",
        retryable=False,
    )
    return workspace


def _indexed_record(store: SecurePlatformStore, workspace: AuditWorkspace, *, indexed_at: str) -> AuditIndexRecord:
    _org, _wsp, _project, prop, environment = store.ensure_local_hierarchy(
        project_name="SaaS reprocess",
        origin="https://example.test",
    )
    return AuditIndexRecord(
        audit_id=workspace.root.name,
        property_id=prop.property_id,
        environment_id=environment.environment_id,
        workspace_path=str(workspace.root.resolve()),
        audit_db_sha256=file_sha256(workspace.database),
        event_time="2026-09-13T12:00:00+00:00",
        status="COMPLETED",
        completion_status="COMPLETE",
        project_name="SaaS reprocess",
        auditor_version="test",
        ruleset_version="test",
        scoring_versions=("SCORE-GEO-004",),
        domains=("example.test",),
        devices=("MOBILE",),
        url_count=1,
        indexed_at=indexed_at,
    )


def test_control_plane_accepts_only_newer_completed_reprocess_digest_revision() -> None:
    _install_platform_revision_gate()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root / "audits")
        with SecurePlatformStore(root / "platform.db") as store:
            first = _indexed_record(store, workspace, indexed_at=utc_now())
            store.upsert_audit(first)

            reprocess_id = start_reprocess_run(workspace, workspace.root.name, source="TEST")
            finish_reprocess_run(
                workspace,
                reprocess_id,
                status=SUCCESS,
                attempted_items=0,
                successful_items=0,
                note="test revision",
            )
            revised = replace(first, audit_db_sha256=file_sha256(workspace.database), indexed_at=utc_now())
            store.upsert_audit(revised)
            assert store.get_audit(first.audit_id).audit_db_sha256 == revised.audit_db_sha256

            # A later disk mutation with no newer RPR must still be rejected. sqlite3
            # Connection's context manager commits/rolls back but does not close the
            # handle, so close explicitly for Windows workspace cleanup.
            import sqlite3
            connection = sqlite3.connect(workspace.database)
            try:
                connection.execute("CREATE TABLE unexpected_mutation(value TEXT)")
                connection.commit()
            finally:
                connection.close()
            tampered = replace(revised, audit_db_sha256=file_sha256(workspace.database), indexed_at=utc_now())
            with pytest.raises(RuntimeError, match="without a newer completed reprocessing revision"):
                store.upsert_audit(tampered)


def test_worker_job_success_is_separate_from_aggregate_audit_completion() -> None:
    from rasai import worker

    _install_worker_reprocess()
    job = SimpleNamespace(
        job_type="AUDIT_REPROCESS",
        payload={"audit_id": "AUD-PARTIAL"},
        property_id="PTY-1",
        environment_id="ENV-1",
    )
    indexed = SimpleNamespace(
        audit_id="AUD-PARTIAL",
        property_id="PTY-1",
        environment_id="ENV-1",
    )

    class Store:
        def get_audit(self, audit_id: str):
            return indexed if audit_id == "AUD-PARTIAL" else None

        def audit_belongs_to_scope(self, audit_id: str, property_id: str, environment_id: str) -> bool:
            return (audit_id, property_id, environment_id) == ("AUD-PARTIAL", "PTY-1", "ENV-1")

    result = SimpleNamespace(
        audit_id="AUD-PARTIAL",
        reprocess_id="RPR-001",
        processing_status="PARTIAL_RETRYABLE",
        score_status="PENDING",
        report_status="PRELIMINARY",
        consolidation_eligible=False,
        attempted_items=1,
        successful_items=0,
        remaining_items=1,
        temporal_expired_items=0,
    )
    with patch("rasai.audit_reprocess.reprocess_audit", return_value=result):
        execution = worker.execute_job(Store(), job, audits_root="audits")

    assert execution.result_ref == "AUD-PARTIAL"
    assert execution.metadata["processing_status"] == "PARTIAL_RETRYABLE"
    assert execution.metadata["report_status"] == "PRELIMINARY"
    assert execution.metadata["consolidation_eligible"] is False
    assert execution.metadata["status_only"] is False


def test_worker_status_only_is_read_only_and_does_not_create_reprocess_history() -> None:
    from rasai import worker

    _install_worker_reprocess()
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory), "AUD-STATUS-ONLY")
        before_hash = file_sha256(workspace.database)
        before = read_summary(workspace, "AUD-STATUS-ONLY")
        assert before is not None
        indexed = SimpleNamespace(
            audit_id="AUD-STATUS-ONLY",
            property_id="PTY-1",
            environment_id="ENV-1",
            workspace_path=str(workspace.root),
        )
        job = SimpleNamespace(
            job_type="AUDIT_REPROCESS",
            payload={"audit_id": "AUD-STATUS-ONLY", "status_only": True},
            property_id="PTY-1",
            environment_id="ENV-1",
        )

        class Store:
            def get_audit(self, audit_id: str):
                return indexed if audit_id == "AUD-STATUS-ONLY" else None

            def audit_belongs_to_scope(self, audit_id: str, property_id: str, environment_id: str) -> bool:
                return (audit_id, property_id, environment_id) == ("AUD-STATUS-ONLY", "PTY-1", "ENV-1")

        with patch("rasai.audit_reprocess.reprocess_audit") as recovery:
            execution = worker.execute_job(Store(), job, audits_root=directory)
        after = read_summary(workspace, "AUD-STATUS-ONLY")

        assert recovery.call_count == 0
        assert after is not None
        assert after.reprocess_count == before.reprocess_count == 0
        assert file_sha256(workspace.database) == before_hash
        assert execution.metadata["status_only"] is True
        assert execution.metadata["reprocess_id"] is None
        assert execution.metadata["processing_status"] == before.processing_status
        assert execution.metadata["consolidation_eligible"] == before.consolidation_eligible


def test_web_job_contract_and_projection_expose_fulfillment_separately() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("pydantic")
    from rasai.web import app as web_app

    _install_web_projection()
    request = web_app.ExecutionJobCreate(
        property_id="PTY-1",
        environment_id="ENV-1",
        job_type="AUDIT_REPROCESS",
        payload={"audit_id": "AUD-WEB"},
    )
    assert request.job_type == "AUDIT_REPROCESS"

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory), "AUD-WEB")
        item = SimpleNamespace(
            audit_id="AUD-WEB",
            property_id="PTY-1",
            environment_id="ENV-1",
            workspace_path=str(workspace.root),
            event_time="2026-09-13T12:00:00+00:00",
            status="COMPLETED",
            completion_status="COMPLETE",
            project_name="Web",
            auditor_version="test",
            ruleset_version="test",
            scoring_versions=("SCORE-GEO-004",),
            domains=("example.test",),
            devices=("MOBILE",),
            url_count=1,
            indexed_at="2026-09-13T12:00:01+00:00",
        )
        projected = web_app._audit_projection(item)

    assert projected["status"] == "COMPLETED"
    assert projected["processing_status"] == "COMPLETE"
    assert projected["score_status"] == "FINAL"
    assert projected["report_status"] == "FINAL"
    assert projected["consolidation_eligible"] is True

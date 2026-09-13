"""SaaS/control-plane integration for AUD fulfillment and selective reprocessing.

This module keeps core audit lifecycle state separate from fulfillment state. A
reprocessing job can finish successfully while the logical AUD still has unresolved
requirements. The platform index keeps the current audit.db digest, but accepts a
digest transition only when a completed RPR run is newer than the previously indexed
revision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Literal

from rasai.audit_fulfillment import read_summary

_INSTALLED = False


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_completed_reprocess(workspace_path: str | Path) -> datetime | None:
    database = Path(workspace_path) / "audit.db"
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        try:
            row = connection.execute(
                """SELECT completed_at FROM audit_reprocess_runs
                   WHERE completed_at IS NOT NULL
                   ORDER BY completed_at DESC LIMIT 1"""
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return _parse_time(row[0]) if row else None


def _install_platform_revision_gate() -> None:
    """Allow audit.db digest changes only after a newly completed RPR revision."""
    from rasai.platform.central_store import CentralPlatformStore

    original = CentralPlatformStore.upsert_audit
    if bool(getattr(original, "_rasai_fulfillment_revision_gate", False)):
        return

    def upsert_audit_with_revision(self: Any, record: Any) -> None:
        existing = self.get_audit(record.audit_id)
        if existing is not None and existing.audit_db_sha256 != record.audit_db_sha256:
            indexed_at = _parse_time(existing.indexed_at)
            reprocessed_at = _latest_completed_reprocess(record.workspace_path)
            if indexed_at is None or reprocessed_at is None or reprocessed_at <= indexed_at:
                raise RuntimeError(
                    f"immutable audit {record.audit_id} changed on disk without a newer completed reprocessing revision"
                )
            # The shared upsert still owns all relational/index fields. Advance only
            # the digest guard first so its normal consistency checks can proceed.
            with self._connection:
                self._connection.execute(
                    "UPDATE audit_index SET audit_db_sha256=? WHERE audit_id=?",
                    (record.audit_db_sha256, record.audit_id),
                )
        original(self, record)

    upsert_audit_with_revision._rasai_fulfillment_revision_gate = True
    upsert_audit_with_revision._rasai_original = original
    CentralPlatformStore.upsert_audit = upsert_audit_with_revision


def _restore_core_platform_snapshot_projection() -> None:
    """Do not overload core status/completion_status with fulfillment state."""
    try:
        from rasai.platform import indexing
    except ImportError:
        return
    current = indexing.read_audit_snapshot
    original = getattr(current, "_rasai_original", None)
    if callable(original) and bool(getattr(current, "_rasai_fulfillment", False)):
        indexing.read_audit_snapshot = original


def _summary_metadata(summary: Any | None, *, audit_id: str, status_only: bool) -> dict[str, Any]:
    if summary is None:
        return {
            "audit_id": audit_id,
            "reprocess_id": None,
            "status_only": status_only,
            "processing_status": None,
            "score_status": None,
            "report_status": None,
            "consolidation_eligible": False,
            "attempted_items": 0,
            "successful_items": 0,
            "remaining_items": None,
            "temporal_expired_items": 0,
        }
    return {
        "audit_id": audit_id,
        "reprocess_id": summary.last_reprocess_id,
        "status_only": status_only,
        "processing_status": summary.processing_status,
        "score_status": summary.score_status,
        "report_status": summary.report_status,
        "consolidation_eligible": summary.consolidation_eligible,
        "attempted_items": 0,
        "successful_items": 0,
        "remaining_items": summary.pending_items + summary.blocked_items,
        "temporal_expired_items": summary.expired_items,
    }


def _install_worker_reprocess() -> None:
    try:
        from rasai import worker
    except ImportError:
        return
    original = worker.execute_job
    if bool(getattr(original, "_rasai_audit_reprocess", False)):
        return

    def execute_job_with_reprocess(store: Any, job: Any, *, audits_root: str | Path = "audits"):
        if str(job.job_type).upper() != "AUDIT_REPROCESS":
            return original(store, job, audits_root=audits_root)

        payload = dict(job.payload or {})
        audit_id = str(payload.get("audit_id") or "").strip()
        indexed = store.get_audit(audit_id)
        if indexed is None:
            raise KeyError(f"audit not found for reprocessing: {audit_id}")
        if hasattr(store, "audit_belongs_to_scope"):
            belongs = bool(
                store.audit_belongs_to_scope(
                    audit_id,
                    job.property_id,
                    job.environment_id,
                )
            )
        else:
            belongs = (
                indexed.property_id == job.property_id
                and indexed.environment_id == job.environment_id
            )
        if not belongs:
            raise ValueError(
                "audit reprocessing job must use the same property/environment scope as the AUD"
            )

        # A status-only durable job is an inspection request, not a recovery pass.
        # It must never create RPR history, mutate audit.db or invoke external work.
        if bool(payload.get("status_only", False)):
            summary = read_summary(Path(indexed.workspace_path), audit_id)
            return worker.WorkerResult(
                result_ref=audit_id,
                metadata=_summary_metadata(summary, audit_id=audit_id, status_only=True),
            )

        from rasai.audit_reprocess import reprocess_audit

        result = reprocess_audit(
            audit_id,
            audits_root=audits_root,
            source="SAAS_WORKER",
        )
        metadata = {
            "audit_id": result.audit_id,
            "reprocess_id": result.reprocess_id,
            "status_only": False,
            "processing_status": result.processing_status,
            "score_status": result.score_status,
            "report_status": result.report_status,
            "consolidation_eligible": result.consolidation_eligible,
            "attempted_items": result.attempted_items,
            "successful_items": result.successful_items,
            "remaining_items": result.remaining_items,
            "temporal_expired_items": result.temporal_expired_items,
        }
        return worker.WorkerResult(result_ref=audit_id, metadata=metadata)

    execute_job_with_reprocess._rasai_audit_reprocess = True
    execute_job_with_reprocess._rasai_original = original
    worker.execute_job = execute_job_with_reprocess


def _install_web_projection() -> None:
    """Expose fulfillment explicitly and allow AUDIT_REPROCESS durable jobs."""
    try:
        from pydantic import BaseModel, Field
        from rasai.web import app as web_app
    except ImportError:
        return

    if not bool(getattr(web_app._audit_projection, "_rasai_fulfillment_projection", False)):
        original_projection = web_app._audit_projection

        def fulfillment_projection(item: Any) -> dict[str, Any]:
            output = original_projection(item)
            summary = read_summary(Path(item.workspace_path), item.audit_id)
            if summary is None:
                output.update(
                    {
                        "processing_status": None,
                        "score_status": None,
                        "report_status": None,
                        "consolidation_eligible": False,
                        "temporal_status": None,
                        "required_items": 0,
                        "successful_items": 0,
                        "pending_items": 0,
                        "blocked_items": 0,
                        "expired_items": 0,
                        "reprocess_count": 0,
                        "last_reprocess_id": None,
                    }
                )
            else:
                output.update(
                    {
                        "processing_status": summary.processing_status,
                        "score_status": summary.score_status,
                        "report_status": summary.report_status,
                        "consolidation_eligible": summary.consolidation_eligible,
                        "temporal_status": summary.temporal_status,
                        "required_items": summary.required_items,
                        "successful_items": summary.successful_items,
                        "pending_items": summary.pending_items,
                        "blocked_items": summary.blocked_items,
                        "expired_items": summary.expired_items,
                        "reprocess_count": summary.reprocess_count,
                        "last_reprocess_id": summary.last_reprocess_id,
                    }
                )
            return output

        fulfillment_projection._rasai_fulfillment_projection = True
        fulfillment_projection._rasai_original = original_projection
        web_app._audit_projection = fulfillment_projection

    if "AUDIT_REPROCESS" not in str(
        web_app.ExecutionJobCreate.model_fields["job_type"].annotation
    ):
        class FulfillmentExecutionJobCreate(BaseModel):
            property_id: str = Field(min_length=1, max_length=200)
            environment_id: str = Field(min_length=1, max_length=200)
            job_type: Literal[
                "AUDIT",
                "AUDIT_REPROCESS",
                "SEARCH_MONITOR",
                "REPORT_REFRESH",
            ]
            payload: dict[str, Any] = Field(default_factory=dict)
            idempotency_key: str | None = Field(default=None, max_length=200)
            priority: int = Field(default=100, ge=0, le=1000)
            max_attempts: int = Field(default=3, ge=1, le=100)

        web_app.ExecutionJobCreate = FulfillmentExecutionJobCreate
        web_app.app = web_app.create_app()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _restore_core_platform_snapshot_projection()
    _install_platform_revision_gate()
    _install_worker_reprocess()
    _install_web_projection()
    _INSTALLED = True

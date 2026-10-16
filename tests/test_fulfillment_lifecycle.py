from __future__ import annotations

import sqlite3

from rasai.audit_fulfillment import (
    COMPLETE,
    LIVE_RECOLLECTION,
    PENDING,
    PROCESSING,
    REPORT_FINAL,
    REPORT_PRELIMINARY,
    SCORE_FINAL,
    SCORE_PENDING,
    SUCCESS,
    list_work_items,
    recalculate,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_resume_runtime import (
    initialize_execution_fulfillment,
    persist_resume_plan,
    resume_plan_options,
)
from rasai.domain import Audit, AuditStatus, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-ISSUE-18"


def _workspace(tmp_path, *, status: AuditStatus = AuditStatus.ACQUIRING) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(
            Audit(
                audit_id=AUDIT_ID,
                project_name="issue 18 lifecycle",
                status=status,
            )
        )
    return workspace


def test_all_materialized_success_is_not_final_while_physical_audit_is_running(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="DISCOVERY_ACQUISITION",
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=SUCCESS,
        retryable=True,
    )

    summary = recalculate(workspace, AUDIT_ID)

    assert summary.required_items == 1
    assert summary.successful_items == 1
    assert summary.processing_status == PROCESSING
    assert summary.score_status == SCORE_PENDING
    assert summary.report_status == REPORT_PRELIMINARY
    assert summary.consolidation_eligible is False


def test_initial_fulfillment_materializes_core_and_planned_requirements_before_collection(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    with resume_plan_options(
        {
            "synthetic_apdex": {
                "enabled": True,
                "threshold_seconds": 3.0,
                "target_valid_samples": 10,
                "max_attempts_per_context": 20,
                "max_pages": 1,
                "timeout_seconds": 30.0,
                "delay_seconds": 1.0,
                "concurrency": 1,
            }
        }
    ):
        persist_resume_plan(
            workspace,
            AUDIT_ID,
            targets=("https://example.test/",),
            target_type="DOMAIN",
            language="pt-BR",
            market="BR",
            max_pages=1,
            device_context="mobile",
            content_remediation=False,
            technical_remediation=False,
        )

    summary = initialize_execution_fulfillment(workspace, AUDIT_ID)
    items = {(item.component, item.scope_key): item for item in list_work_items(workspace, AUDIT_ID)}

    assert items[("CORE_AUDIT", "AUDIT")].status == PENDING
    assert items[("SYNTHETIC_APDEX", "AUDIT")].status == "REQUESTED_NOT_EXECUTED"
    assert summary.processing_status != COMPLETE
    assert summary.consolidation_eligible is False


def test_core_success_only_becomes_final_after_physical_audit_completion(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    persist_resume_plan(
        workspace,
        AUDIT_ID,
        targets=("https://example.test/",),
        target_type="DOMAIN",
        language="pt-BR",
        market="BR",
        max_pages=1,
        device_context="mobile",
        content_remediation=False,
        technical_remediation=False,
    )
    initialize_execution_fulfillment(workspace, AUDIT_ID)
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        scope_key="AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{AUDIT_ID}",
        retryable=False,
    )

    before = recalculate(workspace, AUDIT_ID)
    assert before.processing_status == PROCESSING
    assert before.score_status == SCORE_PENDING
    assert before.report_status == REPORT_PRELIMINARY
    assert before.consolidation_eligible is False

    with AuditPersistence(workspace) as persistence:
        persistence.audits.complete(AUDIT_ID, CompletionStatus.COMPLETE)

    after = recalculate(workspace, AUDIT_ID)
    assert after.processing_status == COMPLETE
    assert after.score_status == SCORE_FINAL
    assert after.report_status == REPORT_FINAL
    assert after.consolidation_eligible is True


def test_repeated_success_reconciliation_preserves_original_success_timestamps(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SYNTHETIC_APDEX",
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=SUCCESS,
        retryable=True,
        configuration={"target_valid_samples": 10},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SYNTHETIC_APDEX",
        scope_key="AUDIT",
        status=SUCCESS,
        result_ref="synthetic-apdex:effective",
        retryable=True,
    )

    original_success = "2026-09-29T12:13:39.594600+00:00"
    original_updated = "2026-09-29T12:13:39.594600+00:00"
    connection = sqlite3.connect(workspace.database)
    try:
        connection.execute(
            """UPDATE audit_fulfillment_work_items
               SET last_success_at=?,updated_at=?
               WHERE audit_id=? AND component='SYNTHETIC_APDEX' AND scope_key='AUDIT'""",
            (original_success, original_updated, AUDIT_ID),
        )
        connection.commit()
    finally:
        connection.close()

    # This mirrors FULFILLMENT_SYNC observing the same persisted successful result
    # during an unrelated catalog-extension RPR.
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SYNTHETIC_APDEX",
        scope_key="AUDIT",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=PENDING,
        retryable=True,
        configuration={"target_valid_samples": 10},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SYNTHETIC_APDEX",
        scope_key="AUDIT",
        status=SUCCESS,
        result_ref="synthetic-apdex:effective",
        retryable=True,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            """SELECT status,last_success_at,updated_at,effective_result_ref
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='SYNTHETIC_APDEX' AND scope_key='AUDIT'""",
            (AUDIT_ID,),
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        SUCCESS,
        original_success,
        original_updated,
        "synthetic-apdex:effective",
    )

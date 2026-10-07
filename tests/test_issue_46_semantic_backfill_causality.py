from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_reprocess import (
    _repair_false_semantic_success,
    _semantic_attempt_succeeded,
    _semantic_backfill_status,
)
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-ISSUE-46"
SNAPSHOT_ID = "SNP-ISSUE-46"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 46"))
    return workspace


def _attempt_table(workspace: AuditWorkspace) -> sqlite3.Connection:
    connection = sqlite3.connect(workspace.database)
    connection.execute(
        """
        CREATE TABLE ai_provider_attempts(
            attempt_id TEXT PRIMARY KEY,
            audit_id TEXT,
            snapshot_id TEXT,
            status TEXT,
            operation TEXT,
            semantic_contract_version TEXT
        )
        """
    )
    return connection


def test_non_semantic_ai_success_cannot_satisfy_semantic_backfill(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = _attempt_table(workspace)
    try:
        with connection:
            connection.executemany(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?)",
                (
                    ("AIA-IMP", AUDIT_ID, SNAPSHOT_ID, "SUCCESS", "IMPROVEMENT_INTELLIGENCE", "IMPROVEMENT-INTELLIGENCE-001"),
                    ("AIA-REQ", AUDIT_ID, SNAPSHOT_ID, "SUCCESS", "REQUEST_REMEDIATION", "REQUEST-REMEDIATION-001"),
                    ("AIA-SEM-1", AUDIT_ID, SNAPSHOT_ID, "TECHNICAL_ERROR", "SEMANTIC_M7", "M18-SEMANTIC-22-v1"),
                ),
            )

        semantic_success = _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        )
        assert semantic_success is False
        assert _semantic_backfill_status(
            successful_attempt=semantic_success,
            assessments=22,
            latest_task_status="FAILED",
        ) == FAILED_RETRYABLE
    finally:
        connection.close()


def test_semantic_m7_success_satisfies_semantic_backfill(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = _attempt_table(workspace)
    try:
        with connection:
            connection.execute(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?)",
                (
                    "AIA-SEM-OK",
                    AUDIT_ID,
                    SNAPSHOT_ID,
                    "SUCCESS",
                    "SEMANTIC_M7",
                    "M18-SEMANTIC-22-v1",
                ),
            )

        assert _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        ) is True
        assert _semantic_backfill_status(
            successful_attempt=True,
            assessments=22,
            latest_task_status="COMPLETE",
        ) == SUCCESS
    finally:
        connection.close()


def test_legacy_null_operation_uses_semantic_contract_not_other_ai_success(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = _attempt_table(workspace)
    try:
        with connection:
            connection.executemany(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?)",
                (
                    ("AIA-IMP", AUDIT_ID, SNAPSHOT_ID, "SUCCESS", None, "IMPROVEMENT-INTELLIGENCE-001"),
                    ("AIA-SEM", AUDIT_ID, SNAPSHOT_ID, "SUCCESS", None, "M18-SEMANTIC-22-v1"),
                ),
            )

        assert _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        ) is True

        with connection:
            connection.execute(
                "DELETE FROM ai_provider_attempts WHERE attempt_id='AIA-SEM'"
            )
        assert _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        ) is False
    finally:
        connection.close()


def test_false_semantic_success_is_repaired_to_retryable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        status=SUCCESS,
        result_ref=f"semantic:{SNAPSHOT_ID}",
    )

    _repair_false_semantic_success(
        workspace,
        audit_id=AUDIT_ID,
        snapshot_id=SNAPSHOT_ID,
    )

    item = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "SEMANTIC_AI"
    )
    assert item.status == FAILED_RETRYABLE
    assert item.retryable is True
    assert item.last_error_code == "SEMANTIC_AI_NO_SUCCESSFUL_CAUSAL_ATTEMPT"
    assert item.effective_result_ref is None


def test_governed_semantic_round_without_provider_ledger_preserves_success(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    connection = _attempt_table(workspace)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE ai_tasks(
                    ai_task_id TEXT PRIMARY KEY,
                    audit_id TEXT,
                    purpose TEXT,
                    scope_key TEXT,
                    semantic_contract_version TEXT,
                    status TEXT,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE ai_request_rounds(
                    ai_round_id TEXT PRIMARY KEY,
                    ai_task_id TEXT,
                    round_index INTEGER,
                    status TEXT,
                    accepted_json TEXT,
                    missing_json TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?)",
                (
                    "AIA-OTHER",
                    AUDIT_ID,
                    SNAPSHOT_ID,
                    "SUCCESS",
                    "IMPROVEMENT_INTELLIGENCE",
                    "IMPROVEMENT-INTELLIGENCE-001",
                ),
            )
            connection.execute(
                "INSERT INTO ai_tasks VALUES (?,?,?,?,?,?,?)",
                (
                    "AIT-SEM-BACKFILL",
                    AUDIT_ID,
                    "SEMANTIC_M7",
                    SNAPSHOT_ID,
                    "M18-SEMANTIC-22-v1",
                    "COMPLETE",
                    "2026-10-07T14:01:21+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO ai_request_rounds VALUES (?,?,?,?,?,?)",
                (
                    "AIR-SEM-BACKFILL",
                    "AIT-SEM-BACKFILL",
                    1,
                    "COMPLETE",
                    '{"BR-GEO-028":{"result":"PASS"}}',
                    "[]",
                ),
            )

        semantic_success = _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        )
        assert semantic_success is True
        assert _semantic_backfill_status(
            successful_attempt=semantic_success,
            assessments=22,
            latest_task_status="COMPLETE",
        ) == SUCCESS
    finally:
        connection.close()


def test_stale_governed_semantic_round_does_not_preserve_success(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = _attempt_table(workspace)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE ai_tasks(
                    ai_task_id TEXT PRIMARY KEY,
                    audit_id TEXT,
                    purpose TEXT,
                    scope_key TEXT,
                    semantic_contract_version TEXT,
                    status TEXT,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE ai_request_rounds(
                    ai_round_id TEXT PRIMARY KEY,
                    ai_task_id TEXT,
                    round_index INTEGER,
                    status TEXT,
                    accepted_json TEXT,
                    missing_json TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO ai_tasks VALUES (?,?,?,?,?,?,?)",
                (
                    "AIT-SEM-STALE",
                    AUDIT_ID,
                    "SEMANTIC_M7",
                    SNAPSHOT_ID,
                    "M18-SEMANTIC-22-v1",
                    "STALE",
                    "2026-10-07T14:01:21+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO ai_request_rounds VALUES (?,?,?,?,?,?)",
                (
                    "AIR-SEM-STALE",
                    "AIT-SEM-STALE",
                    1,
                    "COMPLETE",
                    '{"BR-GEO-028":{"result":"PASS"}}',
                    "[]",
                ),
            )

        assert _semantic_attempt_succeeded(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        ) is False
    finally:
        connection.close()

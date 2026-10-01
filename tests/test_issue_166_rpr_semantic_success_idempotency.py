from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.audit_fulfillment import (
    REPLAY_SAFE,
    SUCCESS,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_reprocess import _semantic_backfill_result_ref
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-ISSUE-166"
SNAPSHOT_ID = "SNP-ISSUE-166"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 166"))
    return workspace


def _row(workspace: AuditWorkspace) -> sqlite3.Row:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT status,attempt_count,last_success_at,effective_result_ref
               FROM audit_fulfillment_work_items
               WHERE audit_id=? AND component='SEMANTIC_AI' AND scope_key=?""",
            (AUDIT_ID, SNAPSHOT_ID),
        ).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def test_semantic_backfill_preserves_existing_success_provenance(tmp_path: Path) -> None:
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
        configuration={"provider": "OPENAI"},
    )
    original_ref = f"semantic:OPENAI:{SNAPSHOT_ID}"
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        status=SUCCESS,
        result_ref=original_ref,
    )
    before = dict(_row(workspace))

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        reconciled_ref = _semantic_backfill_result_ref(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        )
    finally:
        connection.close()

    assert reconciled_ref == original_ref

    # Mirror the SUCCESS branch of _backfill_contract: the registration may reconcile
    # durable configuration, but it must not manufacture a new success event.
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
        configuration={"provider": "OPENAI"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        status=SUCCESS,
        result_ref=reconciled_ref,
    )
    after = dict(_row(workspace))

    assert after["status"] == SUCCESS
    assert after["attempt_count"] == before["attempt_count"]
    assert after["effective_result_ref"] == before["effective_result_ref"] == original_ref
    assert after["last_success_at"] == before["last_success_at"]


def test_semantic_backfill_keeps_canonical_fallback_for_new_work_item(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        result_ref = _semantic_backfill_result_ref(
            connection,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
        )
    finally:
        connection.close()

    assert result_ref == f"semantic:{SNAPSHOT_ID}"

    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=True,
        configuration={"provider": "OPENAI"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        status=SUCCESS,
        result_ref=result_ref,
    )

    row = _row(workspace)
    assert row["status"] == SUCCESS
    assert row["effective_result_ref"] == f"semantic:{SNAPSHOT_ID}"
    assert row["last_success_at"] is not None

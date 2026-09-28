from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rasai.audit_fulfillment import start_reprocess_run
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_ai import _clear_semantic_snapshot
from rasai.semantic_persistence import SemanticPersistence


AUDIT_ID = "AUD-ISSUE-41"
SNAPSHOT_ID = "SNP-ISSUE-41"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 41"))
    return workspace


def _tables(workspace: AuditWorkspace) -> set[str]:
    connection = sqlite3.connect(workspace.database)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()


def test_clear_semantic_snapshot_accepts_audit_that_never_reached_m7(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    before = _tables(workspace)
    assert "semantic_assessments" not in before
    assert "entity_observations" not in before

    _clear_semantic_snapshot(
        workspace,
        audit_id=AUDIT_ID,
        snapshot_id=SNAPSHOT_ID,
        reprocess_id="RPR-ISSUE-41-PRE-M7",
    )

    after_cleanup = _tables(workspace)
    assert "semantic_assessments" not in after_cleanup
    assert "entity_observations" not in after_cleanup

    # M7/SemanticPersistence remains the owner of first schema materialization.
    with SemanticPersistence(workspace):
        pass

    after_m7_boundary = _tables(workspace)
    assert "semantic_assessments" in after_m7_boundary
    assert "entity_observations" in after_m7_boundary


def test_clear_semantic_snapshot_archives_existing_rows_before_replacement(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with SemanticPersistence(workspace):
        pass

    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO semantic_assessments(
                    assessment_id,snapshot_id,assessment_type,result,confidence,evidence_ids,
                    prompt_id,prompt_version,provider,model,configuration_version,reasoning_summary
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "ASM-ISSUE-41",
                    SNAPSHOT_ID,
                    "BR-GEO-038",
                    "PASS",
                    0.95,
                    "[]",
                    "PROMPT-ISSUE-41",
                    "1",
                    "OPENAI",
                    "gpt-test",
                    "1",
                    "prior semantic assessment",
                ),
            )
            connection.execute(
                """
                INSERT INTO entity_observations(
                    entity_observation_id,snapshot_id,name,entity_type,confidence,evidence_ids
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    "ENT-ISSUE-41",
                    SNAPSHOT_ID,
                    "Produto Alpha",
                    "PRODUCT",
                    0.90,
                    "[]",
                ),
            )
    finally:
        connection.close()

    reprocess_id = start_reprocess_run(
        workspace,
        AUDIT_ID,
        source="TEST",
        note="issue 41 archive regression",
    )

    _clear_semantic_snapshot(
        workspace,
        audit_id=AUDIT_ID,
        snapshot_id=SNAPSHOT_ID,
        reprocess_id=reprocess_id,
    )

    connection = sqlite3.connect(workspace.database)
    try:
        semantic_count = connection.execute(
            "SELECT COUNT(*) FROM semantic_assessments WHERE snapshot_id=?",
            (SNAPSHOT_ID,),
        ).fetchone()
        entity_count = connection.execute(
            "SELECT COUNT(*) FROM entity_observations WHERE snapshot_id=?",
            (SNAPSHOT_ID,),
        ).fetchone()
        archived = connection.execute(
            """
            SELECT entity_type,entity_id
            FROM audit_reprocess_derived_archive
            WHERE audit_id=? AND reprocess_id=?
            ORDER BY rowid
            """,
            (AUDIT_ID, reprocess_id),
        ).fetchall()
    finally:
        connection.close()

    assert semantic_count is not None and semantic_count[0] == 0
    assert entity_count is not None and entity_count[0] == 0
    assert {
        ("semantic_assessment", "ASM-ISSUE-41"),
        ("entity_observation", "ENT-ISSUE-41"),
    }.issubset({(str(row[0]), str(row[1])) for row in archived})


def test_clear_semantic_snapshot_does_not_hide_real_sqlite_errors(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE semantic_assessments(assessment_id TEXT PRIMARY KEY)"
            )
    finally:
        connection.close()

    with pytest.raises(sqlite3.OperationalError, match="snapshot_id"):
        _clear_semantic_snapshot(
            workspace,
            audit_id=AUDIT_ID,
            snapshot_id=SNAPSHOT_ID,
            reprocess_id="RPR-ISSUE-41-SQLITE-ERROR",
        )

from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.audit_fulfillment import start_reprocess_run
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_ai import _reset_scores
from rasai.scoring_persistence import ScoringPersistence


AUDIT_ID = "AUD-ISSUE-25"
RPR_ID = "RPR-ISSUE-25"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 25"))
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


def test_reset_scores_accepts_audit_that_never_reached_scoring(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    before = _tables(workspace)
    assert "scores" not in before
    assert "score_contributions" not in before

    _reset_scores(workspace, AUDIT_ID, RPR_ID)

    after_reset = _tables(workspace)
    assert "scores" not in after_reset
    assert "score_contributions" not in after_reset

    # M9 owns first materialization of the scoring schema.
    with ScoringPersistence(workspace):
        pass

    after_m9_boundary = _tables(workspace)
    assert "scores" in after_m9_boundary
    assert "score_contributions" in after_m9_boundary


def test_reset_scores_archives_and_removes_existing_scores(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with ScoringPersistence(workspace):
        pass

    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO scores(
                    score_id,audit_id,dimension,device,value,coverage,confidence,
                    consolidation_status,scoring_version,calculated_at,limitations
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "SCR-ISSUE-25",
                    AUDIT_ID,
                    "OVERALL_READINESS",
                    "MOBILE",
                    75.0,
                    1.0,
                    "HIGH",
                    "CONSOLIDATED",
                    "SCORE-GEO-004",
                    "2026-09-28T10:00:00+00:00",
                    "[]",
                ),
            )
    finally:
        connection.close()

    reprocess_id = start_reprocess_run(
        workspace,
        AUDIT_ID,
        source="TEST",
        note="issue 25 archive regression",
    )
    _reset_scores(workspace, AUDIT_ID, reprocess_id)

    connection = sqlite3.connect(workspace.database)
    try:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM scores WHERE audit_id=?",
            (AUDIT_ID,),
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

    assert remaining is not None and remaining[0] == 0
    assert ("score", "SCR-ISSUE-25") in {
        (str(row[0]), str(row[1]))
        for row in archived
    }

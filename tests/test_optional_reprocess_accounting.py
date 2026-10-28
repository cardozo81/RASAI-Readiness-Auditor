from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from rasai.audit_fulfillment import initialize_contract, start_reprocess_run
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.selective_optional_reprocess import _update_reprocess_counts


AUDIT_ID = "AUD-OPTIONAL-ACCOUNTING"


def test_optional_evaluations_increment_persisted_rpr_counts() -> None:
    with TemporaryDirectory() as directory:
        workspace = AuditWorkspace.create(Path(directory), AUDIT_ID)
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="optional accounting"))
        initialize_contract(workspace, AUDIT_ID)
        reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")

        _update_reprocess_counts(workspace, reprocess_id, attempted=3, successful=2)
        _update_reprocess_counts(workspace, reprocess_id, attempted=1, successful=1)

        connection = sqlite3.connect(workspace.database)
        try:
            row = connection.execute(
                "SELECT attempted_items,successful_items FROM audit_reprocess_runs WHERE reprocess_id=?",
                (reprocess_id,),
            ).fetchone()
        finally:
            connection.close()

        assert row == (4, 3)


def test_optional_counts_are_isolated_by_reprocess_id_and_preserve_audit_identity() -> None:
    with TemporaryDirectory() as directory:
        workspace = AuditWorkspace.create(Path(directory), AUDIT_ID)
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="isolated RPR accounting"))
        initialize_contract(workspace, AUDIT_ID)
        first = start_reprocess_run(workspace, AUDIT_ID, source="TEST")
        second = start_reprocess_run(workspace, AUDIT_ID, source="TEST")

        _update_reprocess_counts(workspace, first, attempted=2, successful=1)
        _update_reprocess_counts(workspace, second, attempted=1, successful=1)
        _update_reprocess_counts(workspace, first, attempted=1, successful=0)

        with sqlite3.connect(workspace.database) as connection:
            rows = connection.execute(
                "SELECT reprocess_id, audit_id, attempted_items, successful_items "
                "FROM audit_reprocess_runs WHERE reprocess_id IN (?, ?)",
                (first, second),
            ).fetchall()
            audit_ids = connection.execute("SELECT audit_id FROM audits").fetchall()

        assert first != second
        assert {row[0]: (row[1], row[2], row[3]) for row in rows} == {
            first: (AUDIT_ID, 3, 1),
            second: (AUDIT_ID, 1, 1),
        }
        assert audit_ids == [(AUDIT_ID,)]

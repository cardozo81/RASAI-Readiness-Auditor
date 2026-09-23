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

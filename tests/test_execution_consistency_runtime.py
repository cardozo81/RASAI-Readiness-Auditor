"""Focused regressions for the governed execution consistency boundary."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from rasai.audit_configuration_reuse import KIND_CONSOLE, load_reusable_audit_configuration
from rasai.audit_configuration_reuse_runtime import configuration_context
from rasai.domain import Audit
from rasai.execution_consistency_runtime import (
    _install_collection_state_normalization,
    _install_configuration_persistence,
    _publication_state,
)
from rasai.persistence import AuditPersistence, AuditWorkspace


def test_unavailable_collector_is_normalized_to_terminal_error() -> None:
    from rasai import audit_phase_runtime as phase
    from rasai.ai_governance import collection_state_is_terminal

    _install_collection_state_normalization()
    state = phase._normalized_state({"collection_state": "UNAVAILABLE"})
    assert state == "ERROR"
    assert collection_state_is_terminal(state) is True


def test_execution_configuration_is_persisted_when_audit_row_is_created(tmp_path: Path) -> None:
    _install_configuration_persistence()
    audit_id = "AUD-EARLY-CONFIG"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    configuration = {
        "targets": ["https://example.com/"],
        "audit_catalog": {"selected": ["CAT-01", "CAT-03"], "items": []},
    }

    with configuration_context(kind=KIND_CONSOLE, configuration=configuration):
        with AuditPersistence(workspace) as persistence:
            persistence.audits.add(Audit(audit_id=audit_id, project_name="early config"))

    loaded = load_reusable_audit_configuration(tmp_path, audit_id, expected_kind=KIND_CONSOLE)
    assert loaded.configuration == configuration
    assert loaded.configuration_hash


def _publication_database(path: Path, *, processing: str, score: str, report: str, eligible: int) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE audits(audit_id TEXT PRIMARY KEY,status TEXT,completion_status TEXT);
                CREATE TABLE audit_fulfillment_contracts(
                    audit_id TEXT,
                    processing_status TEXT,
                    score_status TEXT,
                    report_status TEXT,
                    consolidation_eligible INTEGER
                );
                """
            )
            connection.execute(
                "INSERT INTO audits VALUES(?,?,?)",
                ("AUD-PUBLICATION", "COMPLETED", "COMPLETE"),
            )
            connection.execute(
                "INSERT INTO audit_fulfillment_contracts VALUES(?,?,?,?,?)",
                ("AUD-PUBLICATION", processing, score, report, eligible),
            )
    finally:
        connection.close()


def test_catalog_publication_is_preliminary_until_fulfillment_is_final(tmp_path: Path) -> None:
    database = tmp_path / "partial.db"
    _publication_database(
        database,
        processing="PARTIAL_RETRYABLE",
        score="FINAL",
        report="FINAL",
        eligible=0,
    )
    assert _publication_state(database, "AUD-PUBLICATION") == "PRELIMINARY"

    final_database = tmp_path / "final.db"
    _publication_database(
        final_database,
        processing="COMPLETE",
        score="FINAL",
        report="FINAL",
        eligible=1,
    )
    assert _publication_state(final_database, "AUD-PUBLICATION") == "FINAL"

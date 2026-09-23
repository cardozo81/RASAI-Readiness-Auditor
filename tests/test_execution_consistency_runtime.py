"""Focused regressions for the governed execution consistency boundary."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from rasai.audit_configuration_reuse import KIND_CONSOLE, load_reusable_audit_configuration
from rasai.audit_configuration_reuse_runtime import configuration_context
from rasai.domain import Audit
from rasai.execution_consistency_runtime import (
    _consistent_catalog_sources,
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


def test_consistent_catalog_sources_accepts_shared_connection(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT);
        CREATE TABLE page_snapshots(
            snapshot_id TEXT PRIMARY KEY,
            page_id TEXT,
            main_content_ref TEXT
        );
        CREATE TABLE rule_executions(audit_id TEXT,rule_id TEXT);
        """
    )
    connection.execute("INSERT INTO pages VALUES(?,?)", ("P-1", "AUD-1"))
    connection.execute("INSERT INTO page_snapshots VALUES(?,?,?)", ("S-1", "P-1", "artifacts/main.txt"))
    connection.execute("INSERT INTO rule_executions VALUES(?,?)", ("AUD-1", "BR-GEO-019"))
    connection.commit()

    received = {}

    def base(database_arg, data_arg, catalog_id_arg, *, connection=None):
        received["database"] = database_arg
        received["audit_id"] = data_arg.audit_id
        received["catalog_id"] = catalog_id_arg
        received["connection"] = connection
        return []

    original_base = getattr(_consistent_catalog_sources, "_base", None)
    _consistent_catalog_sources._base = base
    try:
        data = type("Data", (), {"audit_id": "AUD-1"})()
        rows = _consistent_catalog_sources(
            database,
            data,
            "CAT-03",
            connection=connection,
        )
        assert received["connection"] is connection
        assert ("page_snapshots (main_content)", "Conteúdo principal renderizado", 1) in rows
        assert ("rule_executions (content-semantic)", "Validações determinísticas de conteúdo e semântica", 1) in rows
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        if original_base is None:
            delattr(_consistent_catalog_sources, "_base")
        else:
            _consistent_catalog_sources._base = original_base
        connection.close()


def test_catalog_site_uses_latest_late_installed_catalog_renderer() -> None:
    from rasai import catalog_report_page as page
    from rasai import catalog_report_site as site
    from rasai.catalog_projection_consistency import _sync_site_bindings

    original_page = page._catalog_body
    original_site = site._catalog_body

    def latest_renderer(database, data, catalog_id):
        return f"latest:{catalog_id}"

    try:
        page._catalog_body = latest_renderer
        _sync_site_bindings()
        assert site._catalog_body is latest_renderer
    finally:
        page._catalog_body = original_page
        site._catalog_body = original_site

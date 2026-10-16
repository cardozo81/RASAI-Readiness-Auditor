"""#133: a catalog selected for display is not automatically opted in to AI."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rasai.catalog_report_assurance import _canonical_run_materialized


AUD = "AUD-CAT08-NO-AI"


def _database(tmp_path: Path, *, flag: object, requested: bool = False, include_contract: bool = True) -> Path:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE audit_fulfillment_work_items (audit_id TEXT,component TEXT,required INTEGER,status TEXT)"
        )
        connection.execute("CREATE TABLE audit_fulfillment_contracts (audit_id TEXT,configuration TEXT)")
        if include_contract:
            plan = {"resume_plan": {"optional_environment": {}}}
            if flag is not None:
                plan["resume_plan"]["optional_environment"]["RASAI_IMPROVEMENT_INTELLIGENCE"] = flag
            connection.execute(
                "INSERT INTO audit_fulfillment_contracts VALUES (?,?)",
                (AUD, json.dumps(plan)),
            )
        if requested:
            connection.execute(
                "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?,?)",
                (AUD, "IMPROVEMENT_INTELLIGENCE", 1, "REQUESTED_NOT_EXECUTED"),
            )
    return database


def test_cat08_explicitly_disabled_ai_does_not_lose_governance_or_reliability(tmp_path):
    database = _database(tmp_path, flag="false")
    passed, detail = _canonical_run_materialized(database, AUD, "CAT-08")
    assert passed
    assert "explicitamente desabilitada" in detail


def test_cat08_explicitly_enabled_without_run_fails_closed(tmp_path):
    database = _database(tmp_path, flag="true")
    passed, detail = _canonical_run_materialized(database, AUD, "CAT-08")
    assert not passed
    assert "improvement_intelligence_runs" in detail


def test_cat08_disabled_flag_does_not_hide_requested_work_item(tmp_path):
    database = _database(tmp_path, flag="false", requested=True)
    passed, detail = _canonical_run_materialized(database, AUD, "CAT-08")
    assert not passed
    assert "improvement_intelligence_runs" in detail


def test_cat08_legacy_or_unproven_configuration_remains_conservative(tmp_path):
    database = _database(tmp_path, flag=None)
    passed, _ = _canonical_run_materialized(database, AUD, "CAT-08")
    assert not passed


def test_cat08_canonical_run_still_valid_when_explicitly_requested(tmp_path):
    database = _database(tmp_path, flag="true", requested=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE improvement_intelligence_runs(audit_id TEXT,status TEXT)")
        connection.execute(
            "INSERT INTO improvement_intelligence_runs VALUES (?,?)", (AUD, "COMPLETE")
        )
    passed, detail = _canonical_run_materialized(database, AUD, "CAT-08")
    assert passed
    assert "improvement_intelligence_runs" in detail

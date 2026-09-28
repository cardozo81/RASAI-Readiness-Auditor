from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rasai.domain import Audit
from rasai.governed_reprocess_runtime import _terminalized_states
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.standards_metrics import _init, _record, _service_run
from rasai.standards_owned_service_reconciliation import reconcile_owned_service_runs


AUDIT_ID = "AUD-ISSUE-51"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 51"))
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            _init(connection)
            state_info = {
                "requested": True,
                "configured": True,
                "effective_enabled": True,
                "state": "READY",
            }
            for service_id in ("pagespeed", "crux", "open-web-metrics"):
                _service_run(
                    connection,
                    audit_id=AUDIT_ID,
                    service_id=service_id,
                    state_info=state_info,
                )
            connection.execute(
                """CREATE TABLE web_performance_attempts(
                    audit_id TEXT,
                    service TEXT,
                    status TEXT
                )"""
            )
            connection.execute(
                """CREATE TABLE web_performance_observations(
                    audit_id TEXT,
                    field_source TEXT,
                    lcp_p75_ms REAL,
                    inp_p75_ms REAL,
                    cls_p75 REAL,
                    cwv_assessment TEXT
                )"""
            )
    finally:
        connection.close()
    return workspace


def _service_row(workspace: AuditWorkspace, service_id: str) -> sqlite3.Row:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id=?",
            (AUDIT_ID, service_id),
        ).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def test_owner_evidence_reconciles_readiness_without_fabricating_calls(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute(
                "INSERT INTO web_performance_attempts VALUES (?,?,?)",
                (AUDIT_ID, "PAGESPEED_INSIGHTS", "SUCCESS"),
            )
            connection.execute(
                "INSERT INTO web_performance_attempts VALUES (?,?,?)",
                (AUDIT_ID, "CRUX_API", "TECHNICAL_ERROR"),
            )
            connection.execute(
                "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?)",
                (AUDIT_ID, "PAGESPEED_CRUX", 3017.0, 459.0, 0.9, "FAIL"),
            )
            for metric_id, value in (("ttfb_p75", 420.0), ("fcp_p75", 7100.0)):
                _record(
                    connection,
                    audit_id=AUDIT_ID,
                    metric_id=metric_id,
                    label=metric_id,
                    scope="DEVICE_SNAPSHOT",
                    target="https://example.test/",
                    device="MOBILE",
                    state="MEASURED",
                    value=value,
                    unit="ms",
                    source="OPEN-WEB-METRICS-001",
                    methodology="test",
                    relation_degree=1,
                )
    finally:
        connection.close()

    reconciled = reconcile_owned_service_runs(audit_id=AUDIT_ID, workspace=workspace)

    assert reconciled == {
        "pagespeed": "SUCCESS",
        "crux": "SUCCESS",
        "open-web-metrics": "SUCCESS",
    }

    pagespeed = _service_row(workspace, "pagespeed")
    assert pagespeed["state"] == "SUCCESS"
    assert pagespeed["targets_attempted"] == 1
    assert pagespeed["targets_succeeded"] == 1

    crux = _service_row(workspace, "crux")
    assert crux["state"] == "SUCCESS"
    assert crux["targets_attempted"] == 1
    assert crux["targets_succeeded"] == 1
    crux_details = json.loads(crux["details_json"])
    assert crux_details["field_sources"] == ["PAGESPEED_CRUX"]
    assert crux_details["direct_api_attempts"] == 1
    assert crux_details["direct_api_successes"] == 0
    assert crux_details["direct_api_call_implied"] is False

    open_web = _service_row(workspace, "open-web-metrics")
    assert open_web["state"] == "SUCCESS"
    assert open_web["targets_attempted"] == 1
    assert open_web["targets_succeeded"] == 1
    open_web_details = json.loads(open_web["details_json"])
    assert open_web_details["observations"] == 2
    assert open_web_details["observed_contexts"] == 1
    assert open_web_details["external_calls"] == 0


def test_ready_without_owner_evidence_remains_readiness_not_error(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    reconciled = reconcile_owned_service_runs(audit_id=AUDIT_ID, workspace=workspace)

    assert reconciled == {}
    for service_id in ("pagespeed", "crux", "open-web-metrics"):
        row = _service_row(workspace, service_id)
        assert row["state"] == "READY"
        assert row["targets_attempted"] == 0
        assert row["targets_succeeded"] == 0

    projected = _terminalized_states(
        {
            "SERVICE:pagespeed": "READY",
            "SERVICE:crux": "READY",
            "SERVICE:open-web-metrics": "READY",
        }
    )
    assert projected == {
        "SERVICE:pagespeed": "READY",
        "SERVICE:crux": "READY",
        "SERVICE:open-web-metrics": "READY",
    }


def test_real_pagespeed_failure_remains_error(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                "INSERT INTO web_performance_attempts VALUES (?,?,?)",
                (AUDIT_ID, "PAGESPEED_INSIGHTS", "TECHNICAL_ERROR"),
            )
    finally:
        connection.close()

    reconciled = reconcile_owned_service_runs(audit_id=AUDIT_ID, workspace=workspace)

    assert reconciled["pagespeed"] == "ERROR"
    pagespeed = _service_row(workspace, "pagespeed")
    assert pagespeed["state"] == "ERROR"
    assert pagespeed["targets_attempted"] == 1
    assert pagespeed["targets_succeeded"] == 0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from rasai.audit_catalog_extension import (
    _insert_extension,
    effective_catalog_projection,
    extension_readiness,
)
from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_model import _load_data
from rasai.persistence import AuditWorkspace
from rasai.reprocess_policy import reprocess_policy


AUDIT_ID = "AUD-CATALOG-EXTENSION"


def _workspace(tmp_path: Path, *, valid_until: str | None = None) -> AuditWorkspace:
    root = tmp_path / AUDIT_ID
    root.mkdir()
    workspace = AuditWorkspace.open(root)
    configuration = {
        "targets": ["https://example.test/"],
        "audit_catalog": {
            "version": "AUDIT-CATALOG-001",
            "selected": ["CAT-06", "CAT-07"],
            "ai_enabled": False,
            "items": [
                {"id": "CAT-06", "catalog_id": "CAT-06", "selected": True},
                {"id": "CAT-07", "catalog_id": "CAT-07", "selected": True},
            ],
        },
    }
    digest = configuration_hash(configuration)
    con = sqlite3.connect(workspace.database)
    try:
        con.executescript(
            """
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY,
                configuration_json TEXT,
                configuration_hash TEXT
            );
            CREATE TABLE audit_fulfillment_work_items(
                audit_id TEXT,
                component TEXT,
                temporal_mode TEXT,
                valid_until TEXT
            );
            CREATE TABLE audit_reprocess_runs(
                reprocess_id TEXT PRIMARY KEY,
                audit_id TEXT,
                status TEXT,
                configuration TEXT,
                started_at TEXT,
                completed_at TEXT
            );
            """
        )
        con.execute(
            "INSERT INTO audit_execution_configurations VALUES(?,?,?)",
            (AUDIT_ID, json.dumps(configuration, ensure_ascii=False), digest),
        )
        if valid_until:
            for component in ("DISCOVERY_ACQUISITION", "HTTP_ACQUISITION", "RENDER_CAPTURE"):
                con.execute(
                    "INSERT INTO audit_fulfillment_work_items VALUES(?,?,?,?)",
                    (AUDIT_ID, component, "LIVE_RECOLLECTION", valid_until),
                )
        con.commit()
    finally:
        con.close()
    return workspace


def test_effective_projection_keeps_initial_catalogs_and_links_extension_to_rpr(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    workspace = _workspace(tmp_path, valid_until=future)
    extension_id = _insert_extension(
        workspace,
        AUDIT_ID,
        base=("CAT-06", "CAT-07"),
        added=("CAT-10",),
        effective=("CAT-06", "CAT-07", "CAT-10"),
        catalog_items=({"id": "CAT-10", "catalog_id": "CAT-10", "selected": True},),
        configuration={"catalog_extension": {"added": ["CAT-10"]}},
        live_valid_until=future,
    )
    con = sqlite3.connect(workspace.database)
    con.row_factory = sqlite3.Row
    try:
        con.execute(
            "INSERT INTO audit_reprocess_runs VALUES(?,?,?,?,?,?)",
            (
                "RPR-EXT",
                AUDIT_ID,
                "SUCCESS",
                json.dumps(
                    {
                        "execution_context": {
                            "catalog_extension_id": extension_id,
                            "catalog_extension": {"added": ["CAT-10"]},
                        }
                    }
                ),
                "2026-09-29T12:00:00+00:00",
                "2026-09-29T12:01:00+00:00",
            ),
        )
        con.commit()
        selected, items, history = effective_catalog_projection(con, AUDIT_ID)
    finally:
        con.close()

    assert selected == {"CAT-06", "CAT-07", "CAT-10"}
    assert items["CAT-10"]["selected"] is True
    assert history[-1]["extension_id"] == extension_id
    assert history[-1]["reprocess_id"] == "RPR-EXT"
    assert history[-1]["status"] == "SUCCESS"


def test_live_catalog_extension_respects_original_recovery_window(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    workspace = _workspace(tmp_path, valid_until=future)
    ready, _detail, deadline = extension_readiness(workspace, AUDIT_ID, {"CAT-04"})
    assert ready is True
    assert deadline == future

    con = sqlite3.connect(workspace.database)
    try:
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        con.execute(
            "UPDATE audit_fulfillment_work_items SET valid_until=?",
            (past,),
        )
        con.commit()
    finally:
        con.close()

    ready, detail, _deadline = extension_readiness(workspace, AUDIT_ID, {"CAT-04"})
    assert ready is False
    assert "novo AUD" in detail

    # Pure replay/projection remains eligible even after the live window.
    ready, _detail, _deadline = extension_readiness(workspace, AUDIT_ID, {"CAT-03"})
    assert ready is True


def test_report_model_overlays_extension_without_changing_initial_configuration_hash(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _insert_extension(
        workspace,
        AUDIT_ID,
        base=("CAT-06", "CAT-07"),
        added=("CAT-03",),
        effective=("CAT-03", "CAT-06", "CAT-07"),
        catalog_items=({"id": "CAT-03", "catalog_id": "CAT-03", "selected": True},),
        configuration={"catalog_extension": {"added": ["CAT-03"]}},
        live_valid_until=None,
    )
    con = sqlite3.connect(workspace.database)
    try:
        persisted = con.execute(
            "SELECT configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
    finally:
        con.close()

    data = _load_data(AUDIT_ID, workspace.database)

    assert data.selected == {"CAT-03", "CAT-06", "CAT-07"}
    assert data.config_hash == persisted
    assert data.computed_hash == persisted
    assert data.configuration["audit_catalog"]["initial_selected"] == ["CAT-06", "CAT-07"]
    assert data.configuration["audit_catalog"]["extensions"][0]["added"] == ["CAT-03"]


def test_reprocess_policy_persists_extension_context_without_changing_default_contract() -> None:
    with reprocess_policy(
        selected_items=("PASSIVE_SECURITY",),
        use_ai=False,
        execution_context={
            "catalog_extension_id": "CEX-1",
            "catalog_extension": {"added": ["CAT-10"]},
        },
    ) as policy:
        value = policy.as_configuration()

    assert value["selected_items"] == ["PASSIVE_SECURITY"]
    assert value["use_ai"] is False
    assert value["execution_context"]["catalog_extension_id"] == "CEX-1"
    assert value["execution_context"]["catalog_extension"]["added"] == ["CAT-10"]

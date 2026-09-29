from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai.audit_catalog_extension import (
    _insert_extension,
    apply_catalog_extension,
    effective_catalog_ids,
    effective_catalog_projection,
    extension_readiness,
)
from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_model import _load_data
from rasai.console_catalog_plan import set_selected_catalog_ids
from rasai.persistence import AuditWorkspace
from rasai.reprocess_policy import reprocess_policy


AUDIT_ID = "AUD-CATALOG-EXTENSION"


def _workspace(tmp_path: Path, *, valid_until: str | None = None) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
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
                work_item_id TEXT PRIMARY KEY,
                audit_id TEXT,
                component TEXT,
                scope_key TEXT,
                temporal_mode TEXT,
                valid_until TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE audit_fulfillment_attempts(
                work_item_id TEXT
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
                    """INSERT INTO audit_fulfillment_work_items(
                           work_item_id,audit_id,component,scope_key,temporal_mode,valid_until,attempt_count
                       ) VALUES(?,?,?,?,?,?,0)""",
                    (f"WKI-{component}", AUDIT_ID, component, "AUDIT", "LIVE_RECOLLECTION", valid_until),
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


def test_unlinked_requested_extension_does_not_change_effective_catalog(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    extension_id = _insert_extension(
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
    con.row_factory = sqlite3.Row
    try:
        selected, items, history = effective_catalog_projection(con, AUDIT_ID)
    finally:
        con.close()

    assert selected == {"CAT-06", "CAT-07"}
    assert "CAT-03" not in items
    assert history[-1]["extension_id"] == extension_id
    assert history[-1]["status"] == "REQUESTED"
    assert history[-1]["effective"] is False
    assert history[-1]["reprocess_id"] is None


def test_report_model_overlays_linked_extension_without_changing_initial_configuration_hash(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    extension_id = _insert_extension(
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
        con.execute(
            "INSERT INTO audit_reprocess_runs VALUES(?,?,?,?,?,?)",
            (
                "RPR-CAT-03",
                AUDIT_ID,
                "SUCCESS",
                json.dumps(
                    {
                        "execution_context": {
                            "catalog_extension_id": extension_id,
                            "catalog_extension": {"added": ["CAT-03"]},
                        }
                    }
                ),
                "2026-09-29T12:00:00+00:00",
                "2026-09-29T12:01:00+00:00",
            ),
        )
        persisted = con.execute(
            "SELECT configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
        con.commit()
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


def test_apply_extension_failure_before_rpr_is_retryable_and_preserves_original_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import rasai.audit_catalog_extension as extension

    workspace = _workspace(tmp_path)
    con = sqlite3.connect(workspace.database)
    try:
        original_hash = con.execute(
            "SELECT configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
    finally:
        con.close()

    state = SimpleNamespace(
        audits_root=tmp_path,
        target="https://example.test/",
        web_performance=False,
        synthetic_apdex=True,
        apdex_experience=True,
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
    )
    set_selected_catalog_ids(state, ["CAT-06", "CAT-07", "CAT-10"])

    def fail_materialization(*_args, **_kwargs):
        con = sqlite3.connect(workspace.database)
        try:
            con.execute(
                """INSERT INTO audit_fulfillment_work_items(
                       work_item_id,audit_id,component,scope_key,temporal_mode,valid_until,attempt_count
                   ) VALUES(?,?,?,?,?,?,0)""",
                ("WKI-ORPHAN-CAT10", AUDIT_ID, "PASSIVE_SECURITY", "AUDIT", "REPLAY_SAFE", None),
            )
            con.commit()
        finally:
            con.close()
        raise sqlite3.OperationalError("forced catalog extension materialization failure")

    monkeypatch.setattr(extension, "_materialize_added_work", fail_materialization)

    with pytest.raises(sqlite3.OperationalError):
        apply_catalog_extension(state=state, audit_id=AUDIT_ID)

    assert effective_catalog_ids(workspace, AUDIT_ID) == ("CAT-06", "CAT-07")
    assert not hasattr(state, "_rasai_catalog_extension_use_ai")

    con = sqlite3.connect(workspace.database)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """SELECT status,reprocess_id,note FROM audit_catalog_extensions
               WHERE audit_id=? ORDER BY requested_at DESC LIMIT 1""",
            (AUDIT_ID,),
        ).fetchone()
        persisted_hash = con.execute(
            "SELECT configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
        rpr_count = con.execute(
            "SELECT COUNT(*) FROM audit_reprocess_runs WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
        orphan_count = con.execute(
            """SELECT COUNT(*) FROM audit_fulfillment_work_items
               WHERE work_item_id='WKI-ORPHAN-CAT10'""",
        ).fetchone()[0]
    finally:
        con.close()

    assert row is not None
    assert row["status"] == "FAILED_RETRYABLE"
    assert row["reprocess_id"] is None
    assert "OperationalError" in str(row["note"])
    assert rpr_count == 0
    assert orphan_count == 0
    assert persisted_hash == original_hash


def test_console_contains_unexpected_extension_failure_and_returns_to_menu(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    import rasai.console_audit_catalog_extension as console_extension
    import rasai.console_catalog_plan as catalog_plan
    import rasai.console_catalog_ui as catalog_ui

    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    sqlite3.connect(workspace.database).close()

    state = SimpleNamespace(
        audits_root=tmp_path,
        target="https://example.test/",
        status="",
        operation="",
        error="",
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
    )
    console_module = SimpleNamespace(render_header=lambda *_: None)

    monkeypatch.setattr(console_extension, "effective_catalog_ids", lambda *_: ("CAT-06", "CAT-07"))
    monkeypatch.setattr(console_extension, "_load_audit_configuration", lambda *_: ())
    monkeypatch.setattr(console_extension, "_render_catalogs", lambda *_: None)
    monkeypatch.setattr(console_extension, "_choose_ai_mode", lambda *_: False)
    monkeypatch.setattr(console_extension, "confirm_continue", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(catalog_plan, "catalog_status", lambda *_: ("APTO", "ok"))
    monkeypatch.setattr(catalog_ui, "catalog_menu", lambda *_: None)

    def fail_apply(*_args, **_kwargs):
        raise sqlite3.OperationalError("forced console extension failure")

    monkeypatch.setattr(console_extension, "apply_catalog_extension", fail_apply)
    answers = iter(("10", "R", "V"))
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))

    assert console_extension.complement_audit(console_module, state, AUDIT_ID) is False
    output = capsys.readouterr().out
    assert "sessão foi preservada" in output
    assert "OperationalError" in output


def test_pre_rpr_rollback_never_removes_existing_or_attempted_work(
    tmp_path: Path,
) -> None:
    import rasai.audit_catalog_extension as extension

    workspace = _workspace(tmp_path)
    con = sqlite3.connect(workspace.database)
    try:
        con.execute(
            """INSERT INTO audit_fulfillment_work_items(
                   work_item_id,audit_id,component,scope_key,temporal_mode,valid_until,attempt_count
               ) VALUES(?,?,?,?,?,?,0)""",
            ("WKI-EXISTING", AUDIT_ID, "CORE_AUDIT", "AUDIT", "REPLAY_SAFE", None),
        )
        con.execute(
            """INSERT INTO audit_fulfillment_work_items(
                   work_item_id,audit_id,component,scope_key,temporal_mode,valid_until,attempt_count
               ) VALUES(?,?,?,?,?,?,1)""",
            ("WKI-ATTEMPTED", AUDIT_ID, "PASSIVE_SECURITY", "AUDIT", "REPLAY_SAFE", None),
        )
        con.execute(
            "INSERT INTO audit_fulfillment_attempts(work_item_id) VALUES(?)",
            ("WKI-ATTEMPTED",),
        )
        con.execute(
            """INSERT INTO audit_fulfillment_work_items(
                   work_item_id,audit_id,component,scope_key,temporal_mode,valid_until,attempt_count
               ) VALUES(?,?,?,?,?,?,0)""",
            ("WKI-NEW-ZERO", AUDIT_ID, "IMPROVEMENT_INTELLIGENCE", "AUDIT", "REPLAY_SAFE", None),
        )
        con.commit()
    finally:
        con.close()

    removed = extension._rollback_unlinked_extension_work(
        workspace,
        AUDIT_ID,
        preexisting_work_item_ids=frozenset({"WKI-EXISTING"}),
        candidate_components=frozenset(
            {"PASSIVE_SECURITY", "IMPROVEMENT_INTELLIGENCE"}
        ),
    )

    assert removed == ("WKI-NEW-ZERO",)
    con = sqlite3.connect(workspace.database)
    try:
        remaining = {
            row[0]
            for row in con.execute(
                "SELECT work_item_id FROM audit_fulfillment_work_items WHERE audit_id=?",
                (AUDIT_ID,),
            ).fetchall()
        }
    finally:
        con.close()
    assert "WKI-EXISTING" in remaining
    assert "WKI-ATTEMPTED" in remaining
    assert "WKI-NEW-ZERO" not in remaining

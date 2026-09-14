from __future__ import annotations

import builtins
import json
from pathlib import Path
import sqlite3
from types import ModuleType, SimpleNamespace

import pytest

from rasai.audit_management import (
    AuditInventoryFilter,
    execute_deletion,
    filter_inventory,
    inventory,
    plan_deletion,
)


def _audit(
    root: Path,
    audit_id: str,
    *,
    domain: str,
    project: str = "P",
    status: str = "COMPLETED",
    event: str = "2026-09-01T10:00:00+00:00",
    series: str | None = "SER-1",
) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    database = sqlite3.connect(workspace / "audit.db")
    database.execute(
        "CREATE TABLE audits(audit_id TEXT, created_at TEXT, started_at TEXT, "
        "completed_at TEXT, project_name TEXT, status TEXT, completion_status TEXT)"
    )
    database.execute(
        "INSERT INTO audits VALUES (?,?,?,?,?,?,?)",
        (audit_id, event, event, event, project, status, "COMPLETE"),
    )
    database.execute("CREATE TABLE audit_targets(audit_id TEXT, normalized_origin TEXT)")
    database.execute("INSERT INTO audit_targets VALUES (?,?)", (audit_id, f"https://{domain}"))
    database.execute(
        "CREATE TABLE audit_execution_configurations(audit_id TEXT, execution_series_id TEXT)"
    )
    database.execute("INSERT INTO audit_execution_configurations VALUES (?,?)", (audit_id, series))
    database.execute(
        "CREATE TABLE audit_fulfillment_contracts("
        "audit_id TEXT, processing_status TEXT, consolidation_eligible INTEGER)"
    )
    database.execute(
        "INSERT INTO audit_fulfillment_contracts VALUES (?,?,?)",
        (audit_id, "COMPLETE", 1),
    )
    database.commit()
    database.close()
    (workspace / "payload.bin").write_bytes(b"x" * 64)
    return workspace


def _cons(root: Path, cons_id: str, audit_ids: list[str]) -> Path:
    cons = root / "consolidated" / cons_id
    cons.mkdir(parents=True)
    (cons / "report.html").write_text("ok", encoding="utf-8")
    (cons / "manifest.json").write_text(
        json.dumps(
            {
                "cons_id": cons_id,
                "source_audits": [{"audit_id": value} for value in audit_ids],
            }
        ),
        encoding="utf-8",
    )
    return cons


def test_inventory_and_filters(tmp_path: Path) -> None:
    _audit(
        tmp_path,
        "AUD-ONE",
        domain="one.example",
        project="Alpha",
        event="2026-08-01T10:00:00+00:00",
    )
    _audit(
        tmp_path,
        "AUD-TWO",
        domain="two.example",
        project="Beta",
        event="2026-09-01T10:00:00+00:00",
    )

    items = inventory(tmp_path)
    assert {item.audit_id for item in items} == {"AUD-ONE", "AUD-TWO"}

    filtered = filter_inventory(items, AuditInventoryFilter(domain="two.example"))
    assert [item.audit_id for item in filtered] == ["AUD-TWO"]
    assert filtered[0].configuration_reusable is True
    assert filtered[0].consolidation_eligible is True


def test_plan_finds_only_dependent_consolidated_reports(tmp_path: Path) -> None:
    _audit(tmp_path, "AUD-ONE", domain="one.example")
    _audit(tmp_path, "AUD-TWO", domain="two.example")
    _cons(tmp_path, "CONS-A", ["AUD-ONE", "AUD-TWO"])
    _cons(tmp_path, "CONS-B", ["AUD-TWO"])

    impact = plan_deletion(tmp_path, ["AUD-ONE"])

    assert [item.cons_id for item in impact.consolidated] == ["CONS-A"]
    assert impact.reusable_configurations == 1
    assert impact.series_ids == ("SER-1",)


def test_execute_deletes_audit_and_derived_cons_but_not_unrelated(tmp_path: Path) -> None:
    _audit(tmp_path, "AUD-ONE", domain="one.example")
    _audit(tmp_path, "AUD-TWO", domain="two.example")
    _cons(tmp_path, "CONS-A", ["AUD-ONE", "AUD-TWO"])
    _cons(tmp_path, "CONS-B", ["AUD-TWO"])

    impact = plan_deletion(tmp_path, ["AUD-ONE"])
    result = execute_deletion(tmp_path, impact)

    assert result.status == "COMPLETED"
    assert not (tmp_path / "AUD-ONE").exists()
    assert (tmp_path / "AUD-TWO" / "audit.db").is_file()
    assert not (tmp_path / "consolidated" / "CONS-A").exists()
    assert (tmp_path / "consolidated" / "CONS-B" / "manifest.json").is_file()
    ledger = (tmp_path / ".rasai" / "audit-deletions.jsonl").read_text(encoding="utf-8")
    assert "AUD-ONE" in ledger
    assert "COMPLETED" in ledger


def test_active_audit_is_rejected(tmp_path: Path) -> None:
    workspace = _audit(tmp_path, "AUD-RUN", domain="run.example", status="RUNNING")

    with pytest.raises(RuntimeError, match="processamento"):
        plan_deletion(tmp_path, ["AUD-RUN"])

    assert workspace.exists()


def test_stage_failure_rolls_back_entire_batch(tmp_path: Path, monkeypatch) -> None:
    one = _audit(tmp_path, "AUD-ONE", domain="one.example")
    two = _audit(tmp_path, "AUD-TWO", domain="two.example")
    impact = plan_deletion(tmp_path, ["AUD-ONE", "AUD-TWO"])

    import rasai.audit_management as module

    real_move = module._move
    calls = {"count": 0}

    def fail_second(source: Path, destination: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise PermissionError("locked")
        real_move(source, destination)

    monkeypatch.setattr(module, "_move", fail_second)
    result = execute_deletion(tmp_path, impact)

    assert result.status == "ROLLBACK_COMPLETED"
    assert one.exists() and two.exists()
    assert (one / "audit.db").is_file()
    assert (two / "audit.db").is_file()


def test_console_installer_adds_management_entry_without_changing_normal_picker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import rasai.audit_management_console as console_management
    import rasai.console_navigation as navigation

    fake_console = ModuleType("fake_console")
    fake_console.render_header = lambda state: None
    state = SimpleNamespace(
        audits_root=str(tmp_path),
        error="",
        status="",
        operation="",
        audit_id="",
    )
    original_choose = navigation._choose_audit
    called = {"management": 0}
    monkeypatch.setattr(
        console_management,
        "_management_menu",
        lambda console_module, current_state: called.__setitem__(
            "management", called["management"] + 1
        ),
    )
    answers = iter(["G", "V"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    try:
        console_management.install(fake_console)
        assert navigation._choose_audit(state) is None
        assert called["management"] == 1
    finally:
        navigation._choose_audit = original_choose

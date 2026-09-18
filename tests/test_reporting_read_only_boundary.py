from __future__ import annotations

from pathlib import Path


def test_canonical_final_derivations_precede_reporting() -> None:
    from rasai import audit_runner

    source = Path(audit_runner.__file__).read_text(encoding="utf-8")
    reporting = source.index("_set_status(persistence, audit_id, AuditStatus.REPORTING)")
    for marker in (
        "finalize_core_work_item_before_reporting(",
        "persist_current_configuration(workspace.root, audit_id)",
        "ai_exchange_log.persist_ai_exchange_log(",
        "reconcile_before_reporting(workspace=workspace, audit_id=audit_id)",
        "persist_active_outcome_before_reporting(audit_id=audit_id, workspace=workspace)",
    ):
        assert source.index(marker) < reporting


def test_entrypoint_finalizer_has_no_late_audit_db_persistence() -> None:
    from rasai import entrypoint

    source = Path(entrypoint.__file__).read_text(encoding="utf-8")
    start = source.index("def _run_audit_and_finalize")
    end = source.index("\ndef _install_audit_runtime", start)
    block = source[start:end]
    assert "persist_current_configuration(" not in block
    assert "persist_ai_exchange_log(" not in block
    assert "consume_all_ai_executions()" in block

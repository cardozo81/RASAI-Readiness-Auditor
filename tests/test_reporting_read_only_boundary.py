from __future__ import annotations

from pathlib import Path


def test_entrypoint_finalizer_has_no_late_audit_db_persistence() -> None:
    from rasai import entrypoint

    source = Path(entrypoint.__file__).read_text(encoding="utf-8")
    start = source.index("def _run_audit_and_finalize")
    end = source.index("\ndef _install_audit_runtime", start)
    block = source[start:end]
    assert "persist_current_configuration(" not in block
    assert "persist_ai_exchange_log(" not in block
    assert "consume_all_ai_executions()" in block


def test_entrypoint_holds_execution_lease_through_mutable_cli_continuation_only() -> None:
    from rasai import entrypoint

    source = Path(entrypoint.__file__).read_text(encoding="utf-8")
    start = source.index("def _run_audit_and_finalize")
    end = source.index("\ndef _install_audit_runtime", start)
    block = source[start:end]

    acquire = block.index("mutable_session = start_execution_session(")
    release = block.index('state="COMPLETED" if code == 0 else "FAILED"')
    report = block.index("data_completion = finalize_audit_report_site(")

    assert acquire < release < report
    assert 'kind="CONTINUATION"' in block
    assert 'reject_active=True' in block
    assert 'state="INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"' in block

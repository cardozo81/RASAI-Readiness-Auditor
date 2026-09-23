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

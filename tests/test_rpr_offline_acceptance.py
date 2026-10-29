"""Offline physical RPR acceptance using the real persistence and extraction recovery.

No provider, browser, network request or historical AUD is involved.
Run: python -m pytest -q tests/test_rpr_offline_acceptance.py
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    SUCCESS,
    finish_reprocess_run,
    list_work_items,
    start_reprocess_run,
)
from rasai.core_reprocessing import (
    CONTENT_EXTRACTION,
    HTTP_ACQUISITION,
    RENDER_CAPTURE,
    _recover_extraction,
    synchronize_core_work_items,
)
from tests.test_core_reprocessing import _workspace


def test_offline_rpr_recovers_only_missing_extraction_and_preserves_evidence(tmp_path: Path) -> None:
    # Real SQLite workspace and persisted HTML; fixture is isolated under pytest tmp_path.
    workspace = _workspace(tmp_path, render_succeeded=True, rendered_exists=True)
    audit_id = "AUD-CORE-RECOVERY"
    original_html = workspace.root / "artifacts/rendered/core.html"
    html_digest = sha256(original_html.read_bytes()).hexdigest()

    synchronize_core_work_items(workspace, audit_id)
    before = {item.component: item for item in list_work_items(workspace, audit_id)}
    assert before[HTTP_ACQUISITION].status == SUCCESS
    assert before[RENDER_CAPTURE].status == SUCCESS
    assert before[CONTENT_EXTRACTION].status == FAILED_RETRYABLE
    original_successes = {
        name: (item.status, item.attempt_count)
        for name, item in before.items()
        if item.status == SUCCESS
    }

    with sqlite3.connect(workspace.database) as connection:
        evidence_before = tuple(connection.execute(
            "SELECT evidence_id, observed_value FROM evidence ORDER BY evidence_id"
        ))

    # The production RPR run ledger and deterministic replay engine are used directly.
    rpr_id = start_reprocess_run(workspace, audit_id, source="CLI", note="offline acceptance")
    item = before[CONTENT_EXTRACTION]
    recovered, reason, affected = _recover_extraction(workspace, audit_id, item, rpr_id)
    assert recovered is True, reason
    assert reason == "EXTRACTION_RECOVERED"
    assert affected == {"SNP-CORE"}

    synchronize_core_work_items(workspace, audit_id)
    after = {item.component: item for item in list_work_items(workspace, audit_id)}
    assert after[CONTENT_EXTRACTION].status == SUCCESS
    for name, (status, attempts) in original_successes.items():
        assert after[name].status == status
        assert after[name].attempt_count == attempts
    assert sha256(original_html.read_bytes()).hexdigest() == html_digest

    finish_reprocess_run(
        workspace, rpr_id, status="COMPLETED", attempted_items=1, successful_items=1,
        note="offline acceptance: deterministic extraction recovery",
    )
    with sqlite3.connect(workspace.database) as connection:
        evidence_after = tuple(connection.execute(
            "SELECT evidence_id, observed_value FROM evidence ORDER BY evidence_id"
        ))
        run = connection.execute(
            "SELECT audit_id, status, attempted_items, successful_items FROM audit_reprocess_runs "
            "WHERE reprocess_id=?", (rpr_id,),
        ).fetchone()
        assert run == (audit_id, "COMPLETED", 1, 1)
        # Fixture does not create provider attempts; RPR cannot silently generate AI usage.
        assert connection.execute("SELECT count(*) FROM ai_provider_attempts").fetchone()[0] == 0

    # Existing observation must survive, though recovery may append new derived evidence.
    assert set(evidence_before).issubset(set(evidence_after))

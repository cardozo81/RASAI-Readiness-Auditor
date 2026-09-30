"""Regressões isoladas para contadores e conclusão operacional do RPR (#108)."""
from __future__ import annotations

import json
import sqlite3

from rasai import audit_reprocess, governed_reprocess_runtime as governed
from rasai.audit_fulfillment import (
    PENDING, REPLAY_SAFE, finish_reprocess_run, initialize_contract,
    recalculate, register_work_item, start_reprocess_run,
)
from rasai.domain import Audit
from rasai.operational_log import operational_log_path
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.selective_reprocess_context import scope


AUDIT_ID = "AUD-ACCOUNTING-108"


def _workspace(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="accounting"))
    initialize_contract(workspace, AUDIT_ID)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="WEB_PERFORMANCE",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=PENDING,
        retryable=True,
    )
    recalculate(workspace, AUDIT_ID)
    return workspace


def test_blocked_navigation_never_counts_as_a_reprocess_attempt() -> None:
    preparation = governed.ReprocessPreparation(
        snapshot=None,
        recovered={
            "SYNTHETIC_APDEX": "WAITING_FOR_DATA",
            "PASSIVE_SECURITY": "SUCCESS",
            "WEB_PERFORMANCE": "FAILED_RETRYABLE",
            "SEARCH_INTELLIGENCE": "FAILED_RETRYABLE",
        },
        evaluated_optional=frozenset({"SEARCH_INTELLIGENCE"}),
        sealed_new_evidence=True,
    )
    with scope(AUDIT_ID, {"SEARCH_INTELLIGENCE"}) as state:
        # One optional collector has a causal ledger record; the blocked
        # Navigation Apdex has no adapter attempt and must contribute zero.
        state.extra_attempted = 1
        state.extra_successful = 0
        assert governed._additional_reprocess_counts(preparation, AUDIT_ID) == (3, 1)
        # The outer optional wrapper must not increment a closed ledger again.
        assert (state.extra_attempted, state.extra_successful) == (0, 0)
    # Without the optional facade, only explicitly evaluated optional items count.
    assert governed._additional_reprocess_counts(preparation, AUDIT_ID) == (3, 1)


def test_stage_and_final_event_have_distinct_names_and_persisted_counters(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")

    def emit(*, owner=False):
        return audit_reprocess.emit_reprocess_completion_event(
            workspace,
            AUDIT_ID,
            run_id,
            selected_items=2,
            unselected_items=1,
            skipped_success_items=7,
            use_ai=False,
            ai_used=False,
            final_owner=owner,
        )

    token = audit_reprocess._RPR_FINAL_EVENT_DEFERRED.set(True)
    try:
        assert emit() is False
        finish_reprocess_run(
            workspace, run_id, status="SUCCESS", attempted_items=3, successful_items=1
        )
        # Even a closed internal ledger is not a final event while the
        # outer resume/session/report owner has not completed.
        assert emit() is False
        assert emit(owner=True) is True
    finally:
        audit_reprocess._RPR_FINAL_EVENT_DEFERRED.reset(token)

    events = [
        json.loads(line)
        for line in operational_log_path(workspace).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stages = [event for event in events if event["event"] == "AUDIT_REPROCESS_STAGE_COMPLETED"]
    finals = [event for event in events if event["event"] == "AUDIT_REPROCESS_COMPLETED"]
    assert len(stages) == 2
    assert len(finals) == 1
    final = finals[0]
    with sqlite3.connect(workspace.database) as connection:
        stored = connection.execute(
            "SELECT attempted_items,successful_items FROM audit_reprocess_runs WHERE reprocess_id=?",
            (run_id,),
        ).fetchone()
    assert (final["attempted_items"], final["successful_items"]) == stored == (3, 1)
    assert final["selected_items"] == 2
    assert final["skipped_success_items"] == 7


def test_incomplete_ledger_never_emits_a_final_event(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")
    assert audit_reprocess.emit_reprocess_completion_event(
        workspace,
        AUDIT_ID,
        run_id,
        selected_items=1,
        unselected_items=0,
        skipped_success_items=0,
        use_ai=True,
        ai_used=False,
        final_owner=True,
    ) is False
    events = operational_log_path(workspace).read_text(encoding="utf-8")
    assert "AUDIT_REPROCESS_COMPLETED" not in events
    assert "AUDIT_REPROCESS_STAGE_COMPLETED" in events

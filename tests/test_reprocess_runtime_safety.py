from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    SUCCESS,
    finish_reprocess_run,
    initialize_contract,
    list_work_items,
    read_summary,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_runtime_safety import (
    _M20_CONTEXT,
    _M20RecoveryContext,
    _install_m20_factory_hook,
    record_reprocess_evaluation,
)


AUDIT_ID = "AUD-RPR-SAFETY"


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="RPR safety"))
    initialize_contract(workspace, AUDIT_ID)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="WEB_PERFORMANCE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status=FAILED_RETRYABLE,
    )
    return workspace


def _item(workspace: AuditWorkspace):
    return next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "WEB_PERFORMANCE"
    )


def test_generic_rpr_evaluations_are_append_only_and_linked_to_each_reprocess() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        first_rpr = start_reprocess_run(workspace, AUDIT_ID)
        record_reprocess_evaluation(
            workspace,
            item=_item(workspace),
            reprocess_id=first_rpr,
            metadata={"phase": "first"},
        )
        finish_reprocess_run(
            workspace,
            first_rpr,
            status=FAILED_RETRYABLE,
            attempted_items=1,
            successful_items=0,
        )

        second_rpr = start_reprocess_run(workspace, AUDIT_ID)
        set_work_item_status(
            workspace,
            audit_id=AUDIT_ID,
            component="WEB_PERFORMANCE",
            status=SUCCESS,
            result_ref="web-performance:effective",
        )
        record_reprocess_evaluation(
            workspace,
            item=_item(workspace),
            reprocess_id=second_rpr,
            metadata={"phase": "second"},
        )
        finish_reprocess_run(
            workspace,
            second_rpr,
            status=SUCCESS,
            attempted_items=1,
            successful_items=1,
        )

        item = _item(workspace)
        summary = read_summary(workspace, AUDIT_ID)
        assert item.status == SUCCESS
        assert item.attempt_count == 2
        assert summary is not None and summary.total_attempts == 2

        connection = sqlite3.connect(workspace.database)
        try:
            rows = connection.execute(
                """SELECT reprocess_id,attempt_number,status,metadata
                   FROM audit_fulfillment_attempts
                   WHERE audit_id=? ORDER BY attempt_number""",
                (AUDIT_ID,),
            ).fetchall()
        finally:
            connection.close()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            (first_rpr, 1, FAILED_RETRYABLE),
            (second_rpr, 2, SUCCESS),
        ]
        assert all("REPROCESS_EVALUATION" in str(row[3]) for row in rows)


def test_m20_recovery_context_is_thread_local_and_factory_binding_is_stable(monkeypatch) -> None:
    from rasai import m20

    def base_factory(provider):
        return SimpleNamespace(
            providers=(provider,),
            strategy="TEST",
            analyze=lambda _request: None,
            consume_attempts=lambda: (),
        )

    monkeypatch.setattr(m20, "build_content_remediation_router", base_factory)
    _install_m20_factory_hook()
    installed = m20.build_content_remediation_router

    def run(snapshot_id: str):
        token = _M20_CONTEXT.set(_M20RecoveryContext(frozenset({snapshot_id})))
        try:
            router = m20.build_content_remediation_router(snapshot_id)
            return frozenset(router.successful), m20.build_content_remediation_router
        finally:
            _M20_CONTEXT.reset(token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run, "SNP-A")
        future_b = executor.submit(run, "SNP-B")
        result_a = future_a.result()
        result_b = future_b.result()

    assert result_a[0] == frozenset({"SNP-A"})
    assert result_b[0] == frozenset({"SNP-B"})
    assert result_a[1] is installed
    assert result_b[1] is installed
    assert m20.build_content_remediation_router is installed

    # Outside an RPR context the same stable factory returns the normal router.
    plain = m20.build_content_remediation_router("NORMAL")
    assert not hasattr(plain, "successful")

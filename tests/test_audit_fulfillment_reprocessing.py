"""Contracts for selective AUD recovery and final-report eligibility."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from rasai.audit_fulfillment import (
    COMPLETE,
    EXPIRED_FOR_COMPLETION,
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    PARTIAL_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    begin_attempt,
    finish_attempt,
    finish_reprocess_run,
    initialize_contract,
    list_work_items,
    project_report_validity,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
)
from rasai.audit_reprocess import reprocess_audit
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


def _workspace(root: Path, audit_id: str = "AUD-TEST") -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="fulfillment test"))
        audit = persistence.audits.get(audit_id)
        assert audit is not None
        persistence.audits.complete(audit_id, completion_status=audit.completion_status or __import__("rasai.domain", fromlist=["CompletionStatus"]).CompletionStatus.COMPLETE)
    return workspace


def test_required_contract_controls_final_score_report_and_consolidation() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        initialize_contract(workspace, "AUD-TEST", {"semantic_ai_requested": True})
        register_work_item(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",required=True,
            temporal_mode=REPLAY_SAFE,status=SUCCESS,retryable=False,
        )
        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",status=SUCCESS,
            result_ref="audit:AUD-TEST",retryable=False,
        )
        register_work_item(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            required=True,temporal_mode=REPLAY_SAFE,status=FAILED_RETRYABLE,
        )
        register_work_item(
            workspace,audit_id="AUD-TEST",component="WEB_PERFORMANCE",required=True,
            temporal_mode=LIVE_RECOLLECTION,status=FAILED_RETRYABLE,
            valid_until=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
        )

        partial = recalculate(workspace,"AUD-TEST")
        assert partial.processing_status == PARTIAL_RETRYABLE
        assert partial.score_status == "PENDING"
        assert partial.report_status == "PRELIMINARY"
        assert partial.consolidation_eligible is False

        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="WEB_PERFORMANCE",status=SUCCESS,
            result_ref="web-performance:effective",
        )
        assert recalculate(workspace,"AUD-TEST").processing_status == PARTIAL_RETRYABLE

        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            status=SUCCESS,result_ref="semantic:SNP-1:effective",
        )
        final = recalculate(workspace,"AUD-TEST")
        assert final.processing_status == COMPLETE
        assert final.score_status == "FINAL"
        assert final.report_status == "FINAL"
        assert final.consolidation_eligible is True


def test_attempt_history_is_append_only_across_n_reprocess_runs() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        initialize_contract(workspace,"AUD-TEST")
        register_work_item(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            required=True,temporal_mode=REPLAY_SAFE,status=FAILED_RETRYABLE,
        )
        first = begin_attempt(workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1")
        finish_attempt(
            workspace,first,status=FAILED_RETRYABLE,error_class="NETWORK",error_code="HTTP_503",
            error_message="temporary provider failure",
        )
        rpr1 = start_reprocess_run(workspace,"AUD-TEST")
        second = begin_attempt(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",reprocess_id=rpr1,
        )
        finish_attempt(
            workspace,second,status=FAILED_RETRYABLE,error_class="RATE_LIMIT",error_code="HTTP_429",
            error_message="retry later",
        )
        finish_reprocess_run(workspace,rpr1,status=FAILED_RETRYABLE,attempted_items=1,successful_items=0)
        rpr2 = start_reprocess_run(workspace,"AUD-TEST")
        third = begin_attempt(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",reprocess_id=rpr2,
        )
        finish_attempt(workspace,third,status=SUCCESS,result_ref="semantic:SNP-1:effective")
        summary = finish_reprocess_run(workspace,rpr2,status=SUCCESS,attempted_items=1,successful_items=1)

        item = list_work_items(workspace,"AUD-TEST")[0]
        assert item.status == SUCCESS
        assert item.attempt_count == 3
        assert summary.total_attempts == 3
        assert summary.reprocess_count == 2
        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            status=FAILED_RETRYABLE,error_code="SHOULD_NOT_REGRESS",
        )
        assert list_work_items(workspace,"AUD-TEST")[0].status == SUCCESS


def test_expired_live_recovery_cannot_promote_audit_to_final() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        initialize_contract(workspace,"AUD-TEST")
        register_work_item(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",required=True,
            temporal_mode=REPLAY_SAFE,status=SUCCESS,retryable=False,
        )
        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",status=SUCCESS,
            result_ref="audit:AUD-TEST",retryable=False,
        )
        register_work_item(
            workspace,audit_id="AUD-TEST",component="WEB_PERFORMANCE",required=True,
            temporal_mode=LIVE_RECOLLECTION,status=FAILED_RETRYABLE,
            valid_until=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
        )
        summary = recalculate(workspace,"AUD-TEST")
        assert summary.processing_status == EXPIRED_FOR_COMPLETION
        assert summary.score_status == "UNAVAILABLE"
        assert summary.report_status == "PRELIMINARY"
        assert summary.consolidation_eligible is False
        assert summary.expired_items == 1


def test_report_validity_persists_preliminary_then_final_fulfillment_state() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        initialize_contract(workspace,"AUD-TEST")
        register_work_item(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",required=True,
            temporal_mode=REPLAY_SAFE,status=SUCCESS,retryable=False,
        )
        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",status=SUCCESS,
            result_ref="audit:AUD-TEST",retryable=False,
        )
        register_work_item(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            required=True,temporal_mode=REPLAY_SAFE,status=FAILED_RETRYABLE,
        )

        preliminary = project_report_validity(audit_id="AUD-TEST",workspace=workspace)
        assert preliminary.processing_status == PARTIAL_RETRYABLE
        assert preliminary.score_status == "PENDING"
        assert preliminary.report_status == "PRELIMINARY"
        assert preliminary.consolidation_eligible is False

        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="SEMANTIC_AI",scope_key="SNP-1",
            status=SUCCESS,result_ref="semantic:SNP-1:effective",
        )
        final = project_report_validity(audit_id="AUD-TEST",workspace=workspace)
        assert final.processing_status == COMPLETE
        assert final.score_status == "FINAL"
        assert final.report_status == "FINAL"
        assert final.consolidation_eligible is True


def test_reprocess_materializes_catalog_after_run_is_closed(monkeypatch, tmp_path: Path) -> None:
    from rasai import report_completion

    workspace = _workspace(tmp_path)
    initialize_contract(workspace, "AUD-TEST")
    register_work_item(
        workspace, audit_id="AUD-TEST", component="CORE_AUDIT", required=True,
        temporal_mode=REPLAY_SAFE, status=SUCCESS, retryable=False,
    )
    set_work_item_status(
        workspace, audit_id="AUD-TEST", component="CORE_AUDIT", status=SUCCESS,
        result_ref="audit:AUD-TEST", retryable=False,
    )
    register_work_item(
        workspace, audit_id="AUD-TEST", component="WEB_PERFORMANCE", required=True,
        temporal_mode=LIVE_RECOLLECTION, status=FAILED_RETRYABLE,
        valid_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
    )

    observed: list[tuple[str, str | None]] = []

    def materialize(*, audit_id: str, workspace: AuditWorkspace):
        connection = sqlite3.connect(workspace.database)
        try:
            row = connection.execute(
                "SELECT status,completed_at FROM audit_reprocess_runs "
                "WHERE audit_id=? ORDER BY started_at DESC LIMIT 1",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()
        observed.append((str(row[0]), row[1]))
        return None

    monkeypatch.setattr(report_completion, "materialize_catalog_report_projection", materialize)
    monkeypatch.setattr(
        "rasai.reprocess_measurements.recover_web_performance",
        lambda **_kwargs: True,
    )

    result = reprocess_audit("AUD-TEST", audits_root=tmp_path)

    assert result.processing_status == COMPLETE
    assert observed
    assert observed[-1][0] == SUCCESS
    assert observed[-1][1] is not None


def test_reprocess_is_noop_after_success_and_does_not_repeat_successful_item() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        initialize_contract(workspace,"AUD-TEST")
        register_work_item(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",required=True,
            temporal_mode=REPLAY_SAFE,status=SUCCESS,retryable=False,
        )
        set_work_item_status(
            workspace,audit_id="AUD-TEST",component="CORE_AUDIT",status=SUCCESS,
            result_ref="audit:AUD-TEST",retryable=False,
        )
        register_work_item(
            workspace,audit_id="AUD-TEST",component="WEB_PERFORMANCE",required=True,
            temporal_mode=LIVE_RECOLLECTION,status=FAILED_RETRYABLE,
            valid_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        )

        # The fake recovery below does not materialize the real M21 tables/artifacts.
        # Model the postcondition that a genuine successful recovery would satisfy so
        # the composed runtime can test its no-op guarantee rather than fixture integrity.
        with patch("rasai.selective_optional_reprocess._web_performance_integrity", return_value=True):
            with patch("rasai.reprocess_measurements.recover_web_performance", return_value=True) as recovery:
                first = reprocess_audit("AUD-TEST",audits_root=root)
            assert recovery.call_count == 1
            assert first.reprocess_id is not None
            assert first.processing_status == COMPLETE
            assert first.consolidation_eligible is True

            with patch("rasai.reprocess_measurements.recover_web_performance", return_value=True) as recovery:
                second = reprocess_audit("AUD-TEST",audits_root=root)
        assert recovery.call_count == 0
        assert second.reprocess_id is None
        assert second.processing_status == COMPLETE
        assert second.consolidation_eligible is True

def test_m20_exception_does_not_leave_required_work_item_pending() -> None:
    from rasai.audit_fulfillment_runtime import _wrap_m20

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        def fail_m20(*args, **kwargs):
            raise RuntimeError("synthetic orchestration failure")

        wrapped = _wrap_m20(fail_m20)
        try:
            wrapped(audit_id="AUD-TEST", workspace=workspace, enabled=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected synthetic M20 failure")

        item = next(
            item
            for item in list_work_items(workspace, "AUD-TEST")
            if item.component == "CONTENT_REMEDIATION_AI"
        )
        assert item.status == FAILED_RETRYABLE
        assert item.last_error_class == "ORCHESTRATION"
        assert item.last_error_code == "CONTENT_REMEDIATION_EXECUTION_FAILURE"


def _experience_config_for_fulfillment_test() -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        target_samples_per_page=100,
        max_attempts_per_page=125,
        max_pages=1,
        device_mix=(("MOBILE", 60.0), ("DESKTOP", 40.0)),
        session_mode="cold",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=3.0,
        frustrated_threshold_seconds=12.0,
        errors_affect_apdex=True,
        error_scope="all",
        settle_seconds=5.0,
        delay_seconds=1.0,
        concurrency=1,
    )


def test_m25_initial_execution_records_one_physical_fulfillment_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from rasai.audit_fulfillment_runtime import _wrap_m25

    workspace = _workspace(tmp_path)
    config = _experience_config_for_fulfillment_test()
    observed_calls: list[str] = []

    def execute_m25(**_kwargs):
        observed_calls.append("physical")
        return SimpleNamespace(
            status="SUCCESS",
            attempted_samples=100,
            valid_samples=100,
        )

    monkeypatch.setattr(
        "rasai.audit_fulfillment_runtime._m25_effective_success",
        lambda *_args: True,
    )

    result = _wrap_m25(execute_m25)(
        audit_id="AUD-TEST",
        workspace=workspace,
        config=config,
    )

    assert result.status == "SUCCESS"
    assert observed_calls == ["physical"]
    item = next(
        item
        for item in list_work_items(workspace, "AUD-TEST")
        if item.component == "EXPERIENCE_APDEX"
    )
    assert item.status == SUCCESS
    assert item.attempt_count == 1
    assert item.effective_result_ref == "experience-apdex:effective"

    connection = sqlite3.connect(workspace.database)
    try:
        attempts = connection.execute(
            """SELECT a.status,a.reprocess_id,a.attempt_number
               FROM audit_fulfillment_attempts a
               JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id
               WHERE a.audit_id=? AND w.component='EXPERIENCE_APDEX'""",
            ("AUD-TEST",),
        ).fetchall()
    finally:
        connection.close()

    assert attempts == [(SUCCESS, None, 1)]


def test_m25_initial_exception_finishes_attempt_as_retryable_failure(
    tmp_path: Path,
) -> None:
    from rasai.audit_fulfillment_runtime import _wrap_m25

    workspace = _workspace(tmp_path)
    config = _experience_config_for_fulfillment_test()

    def fail_m25(**_kwargs):
        raise RuntimeError("synthetic M25 failure")

    wrapped = _wrap_m25(fail_m25)
    try:
        wrapped(audit_id="AUD-TEST", workspace=workspace, config=config)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected M25 failure")

    item = next(
        item
        for item in list_work_items(workspace, "AUD-TEST")
        if item.component == "EXPERIENCE_APDEX"
    )
    assert item.status == FAILED_RETRYABLE
    assert item.attempt_count == 1
    assert item.last_error_code == "M25_RUNTIME_FAILURE"


def test_m25_effective_success_uses_population_target_not_per_device_target(
    tmp_path: Path,
) -> None:
    from rasai.audit_fulfillment_runtime import _m25_effective_success

    workspace = _workspace(tmp_path)
    connection = sqlite3.connect(workspace.database)
    try:
        connection.executescript(
            """
            CREATE TABLE synthetic_ux_apdex_runs(
                audit_id TEXT PRIMARY KEY,
                status TEXT,
                pages_considered INTEGER
            );
            CREATE TABLE synthetic_ux_apdex_summaries(
                audit_id TEXT,
                device TEXT,
                valid_samples INTEGER
            );
            """
        )
        connection.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?)",
            ("AUD-TEST", "SUCCESS", 1),
        )
        connection.executemany(
            "INSERT INTO synthetic_ux_apdex_summaries VALUES (?,?,?)",
            (
                ("AUD-TEST", "MOBILE", 60),
                ("AUD-TEST", "DESKTOP", 40),
                ("AUD-TEST", "POPULATION", 100),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert _m25_effective_success(workspace, "AUD-TEST", 100) is True

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    register_work_item,
)
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_policy import current_policy, item_key, reprocess_policy
import rasai.console_reprocess_final_refinements as final


AUDIT_ID = "AUD-ISSUE-50"
SNAPSHOT_ID = "SNP-ISSUE-50"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue 50"))
    return workspace


def _item(component: str, status: str):
    return SimpleNamespace(
        component=component,
        scope_key=SNAPSHOT_ID,
        status=status,
        required=True,
        retryable=True,
        last_error_code=None,
        last_error_message=None,
        attempt_count=0,
        temporal_mode=REPLAY_SAFE,
        valid_until=None,
    )


def test_console_preview_reads_items_after_deterministic_reconciliation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from rasai import audit_fulfillment, audit_reprocess, persistence

    visible = [_item("IMPROVEMENT_INTELLIGENCE", SUCCESS)]

    def reconcile(_workspace, _audit_id):
        visible.append(_item("SEMANTIC_AI", FAILED_RETRYABLE))
        return None

    monkeypatch.setattr(
        persistence.AuditWorkspace,
        "open",
        staticmethod(lambda _path: object()),
    )
    monkeypatch.setattr(audit_reprocess, "reconcile_reprocess_state", reconcile)
    monkeypatch.setattr(
        audit_fulfillment,
        "list_work_items",
        lambda _workspace, _audit_id: tuple(visible),
    )

    pending, successes = final._work_item_preview(
        SimpleNamespace(audits_root=str(tmp_path)),
        AUDIT_ID,
    )

    assert [item.component for item in pending] == ["SEMANTIC_AI"]
    assert [item.component for item in successes] == ["IMPROVEMENT_INTELLIGENCE"]


def test_policy_expands_selection_after_reconciliation_creates_dependency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from rasai import audit_reprocess

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=FAILED_RETRYABLE,
        retryable=True,
    )

    calls: list[str] = []

    def reconcile(active_workspace, active_audit_id):
        calls.append("reconcile")
        register_work_item(
            active_workspace,
            audit_id=active_audit_id,
            component="CONTENT_EXTRACTION",
            scope_key=SNAPSHOT_ID,
            required=True,
            temporal_mode=REPLAY_SAFE,
            status=FAILED_RETRYABLE,
            retryable=True,
        )
        return None

    monkeypatch.setattr(audit_reprocess, "reconcile_reprocess_state", reconcile)

    semantic = item_key("SEMANTIC_AI", SNAPSHOT_ID)
    content = item_key("CONTENT_EXTRACTION", SNAPSHOT_ID)
    with reprocess_policy(
        selected_items=[semantic],
        use_ai=True,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        selected = current_policy().selected_items
        assert calls == ["reconcile"]
        assert selected is not None
        assert semantic in selected
        assert content in selected


def test_use_ai_false_still_denies_reconciled_ai_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from rasai import audit_reprocess
    from rasai.reprocess_policy import item_executable
    from rasai.audit_fulfillment import list_work_items

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key=SNAPSHOT_ID,
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=FAILED_RETRYABLE,
        retryable=True,
    )
    monkeypatch.setattr(
        audit_reprocess,
        "reconcile_reprocess_state",
        lambda _workspace, _audit_id: None,
    )
    item = next(
        value
        for value in list_work_items(workspace, AUDIT_ID)
        if value.component == "SEMANTIC_AI"
    )

    with reprocess_policy(
        selected_items=[item_key("SEMANTIC_AI", SNAPSHOT_ID)],
        use_ai=False,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        assert item_executable(item) is False

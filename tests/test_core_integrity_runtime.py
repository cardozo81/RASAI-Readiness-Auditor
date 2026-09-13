from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from rasai.audit_fulfillment import (
    BLOCKED,
    SUCCESS,
    initialize_contract,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
from rasai.core_integrity_runtime import install, invalidate_persisted_evidence
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-INTEGRITY"


def _workspace(root: Path) -> AuditWorkspace:
    audit = Audit(audit_id=AUDIT_ID, project_name="integrity invalidation")
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
    initialize_contract(workspace, AUDIT_ID, {"source": "test"})
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="RENDER_CAPTURE",
        scope_key="SNP-1",
        status=SUCCESS,
        retryable=True,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="RENDER_CAPTURE",
        scope_key="SNP-1",
        status=SUCCESS,
        result_ref="artifacts/rendered/SNP-1.html",
        retryable=True,
    )
    return workspace


def _item(workspace: AuditWorkspace):
    return next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "RENDER_CAPTURE" and item.scope_key == "SNP-1"
    )


def test_integrity_loss_can_explicitly_invalidate_prior_success_without_erasing_result_ref() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        changed = invalidate_persisted_evidence(
            workspace,
            audit_id=AUDIT_ID,
            component="RENDER_CAPTURE",
            scope_key="SNP-1",
            error_code="PERSISTED_RENDER_ARTIFACT_MISSING",
            error_message="persisted rendered artifact is missing",
        )
        assert changed is True
        item = _item(workspace)
        assert item.status == BLOCKED
        assert item.retryable is False
        assert item.last_error_class == "INTEGRITY"
        assert item.last_error_code == "PERSISTED_RENDER_ARTIFACT_MISSING"
        assert item.effective_result_ref == "artifacts/rendered/SNP-1.html"


def test_core_projection_wrapper_applies_integrity_exception_only_to_supported_codes() -> None:
    from rasai import core_reprocessing

    install()
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        core_reprocessing._set_item(
            workspace,
            audit_id=AUDIT_ID,
            component="RENDER_CAPTURE",
            scope_key="SNP-1",
            status=BLOCKED,
            temporal_mode="LIVE_RECOLLECTION",
            retryable=False,
            source_captured_at=None,
            configuration={"page_id": "PGE-1"},
            error_code="PERSISTED_RENDER_ARTIFACT_MISSING",
            error_message="persisted rendered artifact is missing",
        )
        assert _item(workspace).status == BLOCKED

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        core_reprocessing._set_item(
            workspace,
            audit_id=AUDIT_ID,
            component="RENDER_CAPTURE",
            scope_key="SNP-1",
            status=BLOCKED,
            temporal_mode="LIVE_RECOLLECTION",
            retryable=False,
            source_captured_at=None,
            configuration={"page_id": "PGE-1"},
            error_code="UNRELATED_RUNTIME_BLOCK",
            error_message="ordinary retry state must not downgrade success",
        )
        assert _item(workspace).status == SUCCESS

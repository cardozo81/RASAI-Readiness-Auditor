from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_fulfillment_runtime import _install_consolidation_gate
from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.models import ConsolidationFilter
from rasai.domain import Audit, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-CONSOLIDATION-GATE"


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="consolidation gate"))
        persistence.audits.complete(AUDIT_ID, completion_status=CompletionStatus.COMPLETE)
    initialize_contract(workspace, AUDIT_ID)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        status=SUCCESS,
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=False,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{AUDIT_ID}",
        retryable=False,
    )
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="SEMANTIC_AI",
        scope_key="SNP-1",
        status=FAILED_RETRYABLE,
        required=True,
        temporal_mode=REPLAY_SAFE,
    )
    return workspace


def test_intact_partial_audit_is_available_as_non_conclusive_consolidation_source() -> None:
    # The installer intentionally patches the class for the lifetime of a production
    # process. Restore the prior binding after this isolated contract test.
    original = ConsolidationIndex.candidate_audits
    _install_consolidation_gate()
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _workspace(root)
            index = ConsolidationIndex(root)
            refresh = index.refresh()
            assert refresh.discovered == 1

            candidates = index.candidate_audits(ConsolidationFilter())
            assert len(candidates) == 1
            assert candidates[0]["audit_id"] == AUDIT_ID

            from rasai.audit_fulfillment import read_summary
            from rasai.diagnostic_closure import source_usable_for_consolidation

            summary = read_summary(workspace, AUDIT_ID)
            assert summary is not None
            assert summary.consolidation_eligible is False
            assert source_usable_for_consolidation(workspace.database, AUDIT_ID) is True

            set_work_item_status(
                workspace,
                audit_id=AUDIT_ID,
                component="SEMANTIC_AI",
                scope_key="SNP-1",
                status=SUCCESS,
                result_ref="semantic:SNP-1:effective",
            )
            candidates = index.candidate_audits(ConsolidationFilter())
            assert len(candidates) == 1
            assert candidates[0]["audit_id"] == AUDIT_ID

            # Resolving fulfillment changes closure, not the logical observation identity.
            assert [row["audit_id"] for row in candidates] == [AUDIT_ID]
    finally:
        ConsolidationIndex.candidate_audits = original

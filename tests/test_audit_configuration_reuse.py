"""Platform-neutral regression contracts for completed-AUD configuration reuse."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from rasai.audit_configuration_reuse import (
    KIND_CONSOLE,
    changed_fields,
    load_reusable_audit_configuration,
    persist_audit_configuration,
)
from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    recalculate,
    register_work_item,
    set_work_item_status,
)
from rasai.consolidation.comparability import configuration_comparability
from rasai.domain import Audit, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace


def _workspace(root: Path, audit_id: str, *, complete: bool) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="configuration reuse"))
        persistence.audits.complete(audit_id, completion_status=CompletionStatus.COMPLETE)
    initialize_contract(workspace, audit_id)
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS if complete else FAILED_RETRYABLE,
        retryable=not complete,
    )
    if complete:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="CORE_AUDIT",
            status=SUCCESS,
            result_ref=f"audit:{audit_id}",
            retryable=False,
        )
    recalculate(workspace, audit_id)
    return workspace


def test_reuse_accepts_only_canonical_consolidation_eligible_audits() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        complete = _workspace(root, "AUD-COMPLETE", complete=True)
        partial = _workspace(root, "AUD-PARTIAL", complete=False)
        persist_audit_configuration(
            complete.root,
            audit_id="AUD-COMPLETE",
            kind=KIND_CONSOLE,
            configuration={"settings": {}, "targets": ["https://example.com/"]},
        )
        persist_audit_configuration(
            partial.root,
            audit_id="AUD-PARTIAL",
            kind=KIND_CONSOLE,
            configuration={"settings": {}, "targets": ["https://example.com/"]},
        )

        loaded = load_reusable_audit_configuration(root, "AUD-COMPLETE", expected_kind=KIND_CONSOLE)
        assert loaded.audit_id == "AUD-COMPLETE"

        with pytest.raises(ValueError, match="somente AUDs com consolidação geral concluída"):
            load_reusable_audit_configuration(root, "AUD-PARTIAL", expected_kind=KIND_CONSOLE)


def test_complete_legacy_audit_without_snapshot_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-NO-SNAPSHOT", complete=True)
        with pytest.raises(ValueError, match="não possui snapshot canônico"):
            load_reusable_audit_configuration(root, "AUD-NO-SNAPSHOT")


def test_lineage_hash_and_changed_fields_are_deterministic() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        first = _workspace(root, "AUD-FIRST", complete=True)
        first_snapshot = persist_audit_configuration(
            first.root,
            audit_id="AUD-FIRST",
            kind=KIND_CONSOLE,
            configuration={"settings": {"console": {"max_pages": "10"}}, "targets": ["https://example.com/"]},
        )
        second = _workspace(root, "AUD-SECOND", complete=True)
        updated = {"settings": {"console": {"max_pages": "20"}}, "targets": ["https://example.com/"]}
        fields = changed_fields(first_snapshot.configuration, updated)
        persist_audit_configuration(
            second.root,
            audit_id="AUD-SECOND",
            kind=KIND_CONSOLE,
            configuration=updated,
            source_audit_id="AUD-FIRST",
            source_configuration_hash=first_snapshot.configuration_hash,
            changed=fields,
            execution_series_id=first_snapshot.execution_series_id,
        )
        loaded = load_reusable_audit_configuration(root, "AUD-SECOND", expected_kind=KIND_CONSOLE)
        assert loaded.execution_series_id == first_snapshot.execution_series_id
        assert loaded.source_audit_id == "AUD-FIRST"
        assert "settings.console.max_pages" in loaded.changed_fields
        assert loaded.configuration_hash != first_snapshot.configuration_hash


def test_configuration_comparability_distinguishes_exact_partial_and_unrelated() -> None:
    exact = configuration_comparability((
        {"audit_id": "AUD-1", "event_time": "2026-01-01", "configuration_hash": "a", "execution_series_id": "SER-1"},
        {"audit_id": "AUD-2", "event_time": "2026-02-01", "configuration_hash": "a", "execution_series_id": "SER-1"},
    ))
    assert exact["pair_status"] == "EXACT"
    assert exact["exact_series"] == 1

    partial = configuration_comparability((
        {"audit_id": "AUD-1", "event_time": "2026-01-01", "configuration_hash": "a", "execution_series_id": "SER-1"},
        {"audit_id": "AUD-2", "event_time": "2026-02-01", "configuration_hash": "b", "execution_series_id": "SER-1", "configuration_changed_fields": ("max_pages",)},
    ))
    assert partial["pair_status"] == "PARTIAL"
    assert partial["partial_series"] == 1
    assert partial["altered_fields"] == ["max_pages"]

    unrelated = configuration_comparability((
        {"audit_id": "AUD-1", "event_time": "2026-01-01", "configuration_hash": "a", "execution_series_id": "SER-1"},
        {"audit_id": "AUD-2", "event_time": "2026-02-01", "configuration_hash": "b", "execution_series_id": "SER-2"},
    ))
    assert unrelated["pair_status"] == "UNRELATED"

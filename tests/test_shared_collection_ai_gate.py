"""Isolated regressions for the common AUD/RPR pre-AI collection gate."""
from __future__ import annotations

import inspect

from rasai.audit_collection_gate import evaluate_collection_readiness
from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    PENDING,
    REPLAY_SAFE,
    SUCCESS,
    WAITING_FOR_DATA,
    initialize_contract,
    register_work_item,
    set_work_item_status,
)
from rasai.persistence import AuditWorkspace


AUDIT_ID = "AUD-SHARED-COLLECTION-GATE"


def _workspace(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    initialize_contract(workspace, AUDIT_ID)
    return workspace


def _item(workspace, component, status, *, scope_key="AUDIT", required=True):
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        scope_key=scope_key,
        required=required,
        temporal_mode=LIVE_RECOLLECTION if component != "CORE_AUDIT" else REPLAY_SAFE,
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        scope_key=scope_key,
        status=status,
    )


def test_no_registered_collection_contract_fails_closed(tmp_path):
    workspace = _workspace(tmp_path)
    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert not state.ready
    assert state.blockers == ("COLLECTION_CONTRACT/AUDIT:NO_REQUIRED_WORK_ITEMS",)


def test_pending_render_and_navigation_block_ai_despite_two_prior_successes(tmp_path):
    workspace = _workspace(tmp_path)
    _item(workspace, "WEB_PERFORMANCE", SUCCESS)
    _item(workspace, "EXPERIENCE_APDEX", SUCCESS)
    _item(workspace, "RENDER_CAPTURE", FAILED_RETRYABLE, scope_key="SNP-1")
    _item(workspace, "SYNTHETIC_APDEX", WAITING_FOR_DATA)
    _item(workspace, "CORE_AUDIT", PENDING)
    _item(workspace, "SEMANTIC_AI", PENDING)
    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert not state.ready
    assert state.required_count == 4
    assert state.blockers == (
        "RENDER_CAPTURE/SNP-1:FAILED_RETRYABLE",
        "SYNTHETIC_APDEX/AUDIT:WAITING_FOR_DATA",
    )

    set_work_item_status(
        workspace, audit_id=AUDIT_ID, component="RENDER_CAPTURE",
        scope_key="SNP-1", status=SUCCESS,
    )
    set_work_item_status(
        workspace, audit_id=AUDIT_ID, component="SYNTHETIC_APDEX", status=SUCCESS,
    )
    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert state.ready
    assert state.required_count == 4
    assert not state.blockers


def test_selected_serp_incomplete_blocks_ai_but_nonrequired_error_does_not(tmp_path):
    workspace = _workspace(tmp_path)
    _item(workspace, "DISCOVERY_ACQUISITION", SUCCESS)
    _item(workspace, "SEARCH_INTELLIGENCE", FAILED_RETRYABLE)
    _item(workspace, "EXTERNAL_OBSERVABILITY", FAILED_RETRYABLE, required=False)
    assert not evaluate_collection_readiness(workspace, AUDIT_ID).ready
    set_work_item_status(
        workspace, audit_id=AUDIT_ID,
        component="SEARCH_INTELLIGENCE", status=NOT_APPLICABLE,
    )
    assert evaluate_collection_readiness(workspace, AUDIT_ID).ready


def test_both_orchestrators_use_gate_and_m24_cli_does_not_run_preseal_ai():
    from rasai import audit_runner, cli_extensions, governed_reprocess_runtime
    initial = inspect.getsource(audit_runner.run_audit)
    rpr = inspect.getsource(governed_reprocess_runtime._install_core_composition)
    registered = inspect.getsource(governed_reprocess_runtime._registered_ai_and_report)
    cli = inspect.getsource(cli_extensions.main)

    assert initial.index("evaluate_collection_readiness(") < initial.index("maybe_explain_source_quality(")
    assert "if explain_source_quality and collection_gate.ready:" in initial
    assert "if collection_gate.ready else {}" in initial
    assert rpr.index("evaluate_collection_readiness(") < rpr.index("result = original(")
    assert "if not collection_gate.ready:" in rpr
    assert registered.index("evaluate_collection_readiness(") < registered.index("_registered_ai_purposes(")
    assert "if gate.ready else frozenset()" in registered
    assert "technical_ai=False," in cli
    assert "semantic_provider=None," in cli

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
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-SHARED-COLLECTION-GATE"


def _workspace(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(
            Audit(audit_id=AUDIT_ID, project_name="Shared AI collection gate")
        )
    initialize_contract(
        workspace,
        AUDIT_ID,
        {"resume_plan": {"schema_version": "TEST", "targets": ["https://example.test/"]}},
    )
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


def test_successful_collector_without_durable_plan_cannot_release_ai(tmp_path):
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="Missing plan"))
    initialize_contract(workspace, AUDIT_ID)
    _item(workspace, "DISCOVERY_ACQUISITION", SUCCESS)

    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert not state.ready
    assert state.blockers == ("COLLECTION_CONTRACT/AUDIT:NO_DURABLE_COLLECTION_PLAN",)


def test_selected_collector_without_runtime_attempt_is_projected_and_blocks_ai(tmp_path):
    from rasai.audit_fulfillment import merge_contract_configuration

    workspace = _workspace(tmp_path)
    merge_contract_configuration(
        workspace,
        AUDIT_ID,
        resume_plan={
            "schema_version": "TEST",
            "targets": ["https://example.test/"],
            "execution_options": {
                "synthetic_apdex": {"enabled": True, "target_valid_samples": 150},
            },
        },
    )
    _item(workspace, "DISCOVERY_ACQUISITION", SUCCESS)
    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert not state.ready
    assert state.required_count == 2
    assert state.blockers == (
        "SYNTHETIC_APDEX/AUDIT:REQUESTED_NOT_EXECUTED",
    )
    assert evaluate_collection_readiness(workspace, AUDIT_ID) == state


def test_gate_event_never_includes_private_url_scope(tmp_path):
    workspace = _workspace(tmp_path)
    _item(
        workspace, "RENDER_CAPTURE", FAILED_RETRYABLE,
        scope_key="https://private.example/?token=not-for-logs",
    )
    state = evaluate_collection_readiness(workspace, AUDIT_ID)
    assert not state.ready
    assert state.blockers == ("RENDER_CAPTURE/SCOPE_REDACTED:FAILED_RETRYABLE",)
    assert "private.example" not in repr(state)


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
    # Inspect the source declaration, not the runtime-installed wrappers.
    from pathlib import Path
    initial = (Path(audit_runner.__file__)).read_text(encoding="utf-8")
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


def test_rpr_finishes_diagnostic_projection_without_any_ai_provider_when_not_ready(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from rasai import governed_reprocess_runtime as runtime
    from rasai.audit_collection_gate import CollectionReadiness

    workspace = _workspace(tmp_path)
    _item(workspace, "RENDER_CAPTURE", FAILED_RETRYABLE, scope_key="SNP-1")
    _item(workspace, "SYNTHETIC_APDEX", WAITING_FOR_DATA)
    calls = []

    monkeypatch.setattr(
        runtime, "_registered_ai_purposes",
        lambda *_args: (_ for _ in ()).throw(AssertionError("AI purpose evaluated")),
    )
    monkeypatch.setattr(
        runtime, "run_registered_ai_phase",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("AI provider called")),
    )
    monkeypatch.setattr(
        runtime, "record_collection_gate",
        lambda *_args, **_kwargs: calls.append("gate-recorded"),
    )
    monkeypatch.setattr(
        runtime, "recalculate",
        lambda *_args: SimpleNamespace(processing_status="PARTIAL_RETRYABLE"),
    )
    monkeypatch.setattr(runtime, "project_report_validity", lambda **_kwargs: None)

    preparation = runtime.ReprocessPreparation(
        snapshot=SimpleNamespace(evidence_snapshot_id="AIE-SEALED"),
        recovered={},
        evaluated_optional=frozenset(),
        sealed_new_evidence=True,
    )
    used_ai = runtime._registered_ai_and_report(
        workspace=workspace,
        audit_id=AUDIT_ID,
        preparation=preparation,
        data_finalizer=lambda **_kwargs: calls.append("derived"),
        directed_finalizer=lambda **_kwargs: calls.append("directed"),
        catalog_finalizer=lambda **_kwargs: calls.append("catalog"),
    )
    assert used_ai is False
    assert calls == ["gate-recorded", "derived"]

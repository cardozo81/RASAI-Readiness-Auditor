from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.audit_fulfillment import (
    NOT_CONFIGURED,
    REQUESTED_NOT_EXECUTED,
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    read_summary,
    recalculate,
    register_work_item,
    set_work_item_status,
    start_reprocess_run,
    update_reprocess_run_configuration,
)
from rasai.consolidation.diagnostic_reporting import materialize_diagnostic_notice
from rasai.consolidation.models import GenerationResult, RefreshResult
from rasai.diagnostic_closure import current_pending, source_usable_for_consolidation
from rasai.domain import Audit, CompletionStatus
from rasai.execution_contract import validate_execution_job_payload
from rasai.improvement_intelligence import ImprovementConfig
from rasai.improvement_intelligence_runtime import _apply_reprocess_ai_policy
from rasai.governed_reprocess_runtime import _outcomes_used_ai
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_policy import (
    item_executable,
    item_key,
    reprocess_policy,
    selected_counts,
)


AUDIT_ID = "AUD-PARTIAL-DIAGNOSTIC"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="partial diagnostic"))
        persistence.audits.complete(AUDIT_ID, completion_status=CompletionStatus.COMPLETE)
    initialize_contract(workspace, AUDIT_ID)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
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
    return workspace


def _required_ai_pending(workspace: AuditWorkspace) -> None:
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="IMPROVEMENT_INTELLIGENCE",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=NOT_CONFIGURED,
        retryable=True,
        configuration={"requested": True, "provider": "none"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="IMPROVEMENT_INTELLIGENCE",
        status=NOT_CONFIGURED,
        error_class="CONFIGURATION",
        error_code="AI_NOT_CONFIGURED",
        error_message="CAT-08 requer IA para fechamento integral",
        retryable=True,
    )


def test_final_reconciliation_preserves_ai_not_authorized_cause(monkeypatch, tmp_path: Path) -> None:
    from rasai import fulfillment_execution_contract as contract
    from rasai.improvement_intelligence import ENABLED_ENV

    workspace = _workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="IMPROVEMENT_INTELLIGENCE",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=REQUESTED_NOT_EXECUTED,
        retryable=True,
        configuration={"requested": True, "required_by": "CAT-08"},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="IMPROVEMENT_INTELLIGENCE",
        status=REQUESTED_NOT_EXECUTED,
        error_class="EXECUTION_POLICY",
        error_code="AI_NOT_AUTHORIZED_FOR_EXECUTION",
        error_message="IA não autorizada nesta AUD",
        retryable=True,
    )
    monkeypatch.setenv(ENABLED_ENV, "true")

    contract._reconcile_requested_improvement(workspace, AUDIT_ID)

    from rasai.audit_fulfillment import list_work_items
    item = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "IMPROVEMENT_INTELLIGENCE"
    )
    assert item.status == REQUESTED_NOT_EXECUTED
    assert item.last_error_code == "AI_NOT_AUTHORIZED_FOR_EXECUTION"
    assert item.last_error_class == "EXECUTION_POLICY"


def test_cat08_rpr_policy_overlays_auto_without_mutating_original_config() -> None:
    original = ImprovementConfig(
        enabled=True,
        provider="none",
        model="",
        reasoning="",
        domains=("SEARCH_RANKING",),
        max_recommendations=12,
        timeout_seconds=90.0,
        language="pt-BR",
    ).validate()

    with reprocess_policy(
        selected_items=[item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")],
        use_ai=True,
        ai_provider="auto",
    ):
        effective = _apply_reprocess_ai_policy(original)

    assert original.provider == "none"
    assert effective.provider == "auto"
    assert effective.model == ""
    assert effective.reasoning == ""
    assert effective.domains == original.domains
    assert effective.max_recommendations == original.max_recommendations
    assert effective.timeout_seconds == original.timeout_seconds
    assert effective.language == original.language


def test_required_ai_not_configured_keeps_audit_partial_but_reportable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _required_ai_pending(workspace)

    summary = recalculate(workspace, AUDIT_ID)

    assert summary.processing_status == "PARTIAL_RETRYABLE"
    assert summary.score_status == "PENDING"
    assert summary.report_status == "PRELIMINARY"
    assert summary.consolidation_eligible is False


def test_current_diagnostic_pending_is_read_only_and_disappears_after_resolution(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _required_ai_pending(workspace)
    before = workspace.database.read_bytes()

    pending = current_pending(workspace.database, AUDIT_ID)

    assert workspace.database.read_bytes() == before
    assert len(pending) == 1
    assert pending[0].component == "IMPROVEMENT_INTELLIGENCE"
    assert pending[0].state == "Não executada - IA não configurada/disponível"

    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component="IMPROVEMENT_INTELLIGENCE",
        status=SUCCESS,
        result_ref="improvement:effective",
        retryable=False,
    )
    assert current_pending(workspace.database, AUDIT_ID) == ()


def test_intact_partial_audit_is_limited_cons_source_without_becoming_final(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _required_ai_pending(workspace)
    summary = recalculate(workspace, AUDIT_ID)

    assert summary.consolidation_eligible is False
    before = workspace.database.read_bytes()
    assert source_usable_for_consolidation(workspace.database, AUDIT_ID) is True
    assert workspace.database.read_bytes() == before


def test_rpr_policy_separates_selected_items_from_ai_authorization() -> None:
    api = SimpleNamespace(component="WEB_PERFORMANCE", scope_key="AUDIT")
    ai = SimpleNamespace(component="IMPROVEMENT_INTELLIGENCE", scope_key="AUDIT")

    with reprocess_policy(
        selected_items=[
            item_key("WEB_PERFORMANCE", "AUDIT"),
            item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT"),
        ],
        use_ai=False,
    ):
        assert item_executable(api) is True
        assert item_executable(ai) is False
        assert selected_counts((api, ai)) == (1, 1)

    with reprocess_policy(
        selected_items=[item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")],
        use_ai=True,
        ai_provider="openai",
        ai_model="gpt-5.6-luna",
        ai_reasoning="HIGH",
    ):
        assert item_executable(api) is False
        assert item_executable(ai) is True
        assert selected_counts((api, ai)) == (1, 1)


def test_rpr_persists_execution_local_policy_without_changing_audit_config(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    selected = [item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")]

    with reprocess_policy(
        selected_items=selected,
        use_ai=True,
        ai_provider="openai",
        ai_model="gpt-5.6-luna",
        ai_reasoning="HIGH",
    ):
        reprocess_id = start_reprocess_run(workspace, AUDIT_ID, source="TEST")
    update_reprocess_run_configuration(workspace, reprocess_id, {"ai_used": True})

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT configuration FROM audit_reprocess_runs WHERE reprocess_id=?",
            (reprocess_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    persisted = json.loads(row[0])
    assert persisted["selected_items"] == selected
    assert persisted["use_ai"] is True
    assert persisted["ai_provider"] == "openai"
    assert persisted["ai_model"] == "gpt-5.6-luna"
    assert persisted["ai_reasoning"] == "HIGH"
    assert persisted["ai_used"] is True


def test_saas_rpr_contract_accepts_selection_and_execution_local_ai_policy() -> None:
    validate_execution_job_payload(
        "AUDIT_REPROCESS",
        {
            "audit_id": AUDIT_ID,
            "selected_items": [
                {"component": "WEB_PERFORMANCE", "scope_key": "AUDIT"},
                {"component": "IMPROVEMENT_INTELLIGENCE", "scope_key": "AUDIT"},
            ],
            "use_ai": True,
            "ai_provider": "openai",
            "ai_model": "gpt-5.6-luna",
            "ai_reasoning": "HIGH",
        },
    )


def test_cons_notice_distinguishes_requested_but_not_configured_ai(tmp_path: Path) -> None:
    report_dir = tmp_path / "CONS-TEST"
    report_dir.mkdir()
    report = report_dir / "report.html"
    manifest = report_dir / "manifest.json"
    report.write_text("<html><body><main><h1>CONS</h1></main></body></html>", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    result = GenerationResult(
        report_dir=report_dir,
        report_path=report,
        manifest_path=manifest,
        reused=False,
        request_fingerprint="fp",
        refresh=RefreshResult(0, 0, 0, 0, ()),
    )

    materialize_diagnostic_notice(
        result,
        {"audits": ()},
        ai_requested=True,
        ai_status="NOT_CONFIGURED",
        ai_reason="AI_PROVIDER_NOT_CONFIGURED",
    )

    html = report.read_text(encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "Fechamento diagnóstico pendente" in html
    assert "Não executada - IA não configurada/disponível" in html
    assert payload["diagnostic_closure"]["status"] == "PENDING"
    assert payload["diagnostic_closure"]["specialist_ai_status"] == "NOT_CONFIGURED"


def test_cons_notice_is_absent_when_everything_is_complete(tmp_path: Path) -> None:
    report_dir = tmp_path / "CONS-COMPLETE"
    report_dir.mkdir()
    report = report_dir / "report.html"
    manifest = report_dir / "manifest.json"
    original = "<html><body><main><h1>CONS</h1></main></body></html>"
    report.write_text(original, encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    result = GenerationResult(
        report_dir=report_dir,
        report_path=report,
        manifest_path=manifest,
        reused=False,
        request_fingerprint="fp",
        refresh=RefreshResult(0, 0, 0, 0, ()),
    )

    materialize_diagnostic_notice(
        result,
        {"audits": ()},
        ai_requested=False,
        ai_status="NOT_REQUESTED",
        ai_reason=None,
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert report.read_text(encoding="utf-8") == original
    assert payload["diagnostic_closure"]["status"] == "COMPLETE"
    assert payload["diagnostic_closure"]["pending_count"] == 0


def test_rpr_ai_used_distinguishes_authorization_from_provider_attempt() -> None:
    assert _outcomes_used_ai(
        {
            "IMPROVEMENT_INTELLIGENCE": {
                "status": "COMPLETE_WITH_LIMITATIONS",
                "reason": "AI_NOT_CONFIGURED",
                "provider": "none",
            }
        }
    ) is False
    assert _outcomes_used_ai(
        {
            "IMPROVEMENT_INTELLIGENCE": {
                "status": "COMPLETE_WITH_LIMITATIONS",
                "reason": "AI_PROVIDER_UNAVAILABLE",
                "provider": "openai",
            }
        }
    ) is True


def test_cons_notice_exposes_non_conclusive_source_without_detailed_work_items(tmp_path: Path) -> None:
    report_dir = tmp_path / "CONS-NON-CONCLUSIVE"
    report_dir.mkdir()
    report = report_dir / "report.html"
    manifest = report_dir / "manifest.json"
    report.write_text("<html><body><main><h1>CONS</h1></main></body></html>", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    result = GenerationResult(
        report_dir=report_dir,
        report_path=report,
        manifest_path=manifest,
        reused=False,
        request_fingerprint="fp",
        refresh=RefreshResult(0, 0, 0, 0, ()),
    )

    materialize_diagnostic_notice(
        result,
        {
            "audits": (
                {
                    "audit_id": "AUD-SOURCE",
                    "conclusive": False,
                    "source_state_label": "Conclusão não comprovada",
                    "required_issues": (),
                    "source_limitations": ("fechamento integral não comprovado",),
                },
            )
        },
        ai_requested=False,
        ai_status="NOT_REQUESTED",
        ai_reason=None,
    )

    html = report.read_text(encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "AUD-SOURCE" in html
    assert "Conclusão não comprovada" in html
    assert "fechamento integral não comprovado" in html
    assert payload["diagnostic_closure"]["status"] == "PENDING"

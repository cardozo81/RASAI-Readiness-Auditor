from __future__ import annotations

from types import SimpleNamespace

from rasai.ai_canonical_orchestration import AiProviderOutcome, invocation_from_diagnostic
from rasai.ai_execution_state import clear_current_ai_execution, set_current_ai_execution
from rasai.ai_orchestration_unification import _current_primary_runtime
from rasai.audit_fulfillment import LIVE_RECOLLECTION, REPLAY_SAFE, list_work_items, register_work_item
from rasai.domain import Audit
from rasai.m18_ai import ProviderDiagnostic, ProviderErrorClass, _classify_http_error as core_classify_http_error
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.provider_extensions import _classify_http_error as extension_classify_http_error
from rasai.render_materiality import CaptureQualityState, resolve_capture_quality
from rasai.search_audit_runtime import ensure_competitive_ai_work_item


def test_http_402_is_terminal_credit_exhaustion_for_all_provider_families() -> None:
    for classifier in (core_classify_http_error, extension_classify_http_error):
        error_class = classifier(402, "unknown_error", "invalid_request_error")
        assert error_class is ProviderErrorClass.CREDIT_ERROR
        invocation = invocation_from_diagnostic(
            ProviderDiagnostic(error_class=error_class, http_status=402)
        )
        assert invocation.outcome is AiProviderOutcome.PROVIDER_TERMINAL


def test_specialist_runtime_reuses_current_auto_execution() -> None:
    class Runtime:
        def session_snapshot(self):
            return {
                "strategy": "AUTO",
                "enabled": True,
                "initial_provider": "OPENAI",
                "initial_model": "gpt-test",
                "initial_reasoning_profile": "NONE",
            }

    runtime = Runtime()
    recorder = object()
    clear_current_ai_execution()
    try:
        set_current_ai_execution(runtime, recorder)
        assert _current_primary_runtime("auto") is runtime
    finally:
        clear_current_ai_execution()


def test_materiality_recovers_empty_main_even_with_large_navigation_text() -> None:
    initial = (
        "<html><body><nav>"
        + ("menu " * 150)
        + "</nav><main id='sk-skeleton'><img loading='lazy'></main></body></html>"
    )
    materialized = (
        "<html><body><nav>menu</nav><main>"
        "<h1>Seguro de Vida Bradesco</h1>"
        "<p>"
        + ("conteudo principal materializado " * 20)
        + "</p></main></body></html>"
    )

    class Page:
        def wait_for_timeout(self, _milliseconds: int) -> None:
            return None

        def content(self) -> str:
            return materialized

    rendered, quality = resolve_capture_quality(
        Page(),
        initial,
        settle_outcome="BOUNDED_TIMEOUT",
        recovery_step_ms=0,
        recovery_observations=1,
    )

    assert rendered == materialized
    assert quality["state"] == CaptureQualityState.RECOVERED.value
    assert quality["reason"] == "TRANSIENT_RENDER_MATERIALIZED"


def test_competitive_ai_requirement_is_backfilled_as_replay_safe(tmp_path) -> None:
    audit_id = "AUD-COMPETITIVE-RPR"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="competitive-rpr"))

    register_work_item(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
        configuration={
            "ai_competitive": True,
            "ai_provider": "auto",
            "ai_model": "",
            "ai_timeout_seconds": 180.0,
            "ymyl_mode": "AUTO",
        },
    )

    item = ensure_competitive_ai_work_item(workspace, audit_id)
    assert item is not None
    assert item.component == "COMPETITIVE_INTELLIGENCE"
    assert item.required is True
    assert item.temporal_mode == REPLAY_SAFE
    assert item.retryable is True

    matching = [
        current
        for current in list_work_items(workspace, audit_id)
        if current.component == "COMPETITIVE_INTELLIGENCE"
    ]
    assert len(matching) == 1

"""Canonical console projection for the governed evidence/AI lifecycle."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


_INSTALLED = False
_CANONICAL_ORDER = (
    "STARTING",
    "INITIALIZING",
    "CORE_COLLECTION",
    "EXTERNAL_COLLECTION",
    "DETERMINISTIC_ANALYSIS",
    "EVIDENCE_SEALING",
    "AI_ANALYSIS",
    "FINAL_DERIVATION",
    "REPORTING",
    "FINALIZING",
)
_EXTERNAL_LEGACY = {
    "WEB_PERFORMANCE",
    "SYNTHETIC_UX_APDEX",
    "SYNTHETIC_APDEX",
    "GSC",
    "EXTERNAL_OBSERVABILITY",
    "SEARCH_INTELLIGENCE",
}


def _weights(model: Any, state: Any) -> dict[str, float]:
    pages = max(int(model._page_count(state)), 1)
    devices = int(model._device_count(state))
    contexts = max(pages * devices, 1)
    ai_enabled = str(getattr(state, "ai_provider", "none")).casefold() != "none"
    external = 1.0
    if model._web_performance_enabled(state):
        external += 14.0 * max(
            model._bounded_pages(getattr(state, "web_max_pages", pages), pages) * devices,
            1,
        )
    if bool(getattr(state, "synthetic_apdex", False)):
        external += 4.0
    if bool(getattr(state, "apdex_experience", False)):
        external += 5.0
    if model._service_ready("google-search-console"):
        external += 5.0
    external += 2.5 * model._external_operation_count(state)
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if queries:
        external += 4.0 * len(queries)

    ai = 1.0
    if ai_enabled:
        ai += 5.0 * contexts
    if bool(getattr(state, "content_remediation", False)) and ai_enabled:
        ai += 5.0 * pages
    if bool(getattr(state, "technical_remediation", False)) and ai_enabled:
        ai += 3.0

    return {
        "STARTING": 0.8,
        "INITIALIZING": 0.8,
        "CORE_COLLECTION": max(7.0, 5.0 * contexts),
        "EXTERNAL_COLLECTION": external,
        "DETERMINISTIC_ANALYSIS": max(4.0, 1.5 * contexts),
        "EVIDENCE_SEALING": 0.8,
        "AI_ANALYSIS": ai,
        "FINAL_DERIVATION": 2.5,
        "REPORTING": 2.0,
        "FINALIZING": 1.2,
    }


def _canonical_phase(model: Any, state: Any, progress: Any | None = None) -> str | None:
    status = str(getattr(state, "status", "")).upper()
    operation = str(getattr(state, "operation", "")).upper()
    if status in model._TERMINAL:
        return status
    if status in _CANONICAL_ORDER:
        return status
    if status in _EXTERNAL_LEGACY:
        return "EXTERNAL_COLLECTION"
    if status in {"DISCOVERING", "ACQUIRING"}:
        return "CORE_COLLECTION"
    if status in {"ANALYZING", "COMPARING"}:
        return "DETERMINISTIC_ANALYSIS"
    if status in {"SCORING", "RECOMMENDING"}:
        return "FINAL_DERIVATION"
    if "AI" in operation and not any(
        token in operation for token in ("CLARITY", "GSC", "CRUX", "PAGESPEED")
    ):
        return "AI_ANALYSIS"
    label = str(getattr(progress, "label", "")).casefold() if progress is not None else ""
    if any(token in label for token in ("search intelligence", "serp", "search console", "web performance", "apdex", "observabilidade")):
        return "EXTERNAL_COLLECTION"
    return None


def _set_progress(
    runtime: Any,
    model: Any,
    state: Any,
    *,
    phase: str,
    stage: float,
    label: str,
    detail: str,
    operation: str,
) -> None:
    state.status = phase
    state.operation = operation
    progress_type = getattr(runtime, "_RunProgress")
    runtime._RUN_PROGRESS[id(state)] = progress_type(
        label=label,
        percent=stage,
        detail=detail,
        exact=True,
        stage_percent=stage,
        stage_exact=True,
        overall_percent=model.projected_overall(state, phase, stage),
        overall_exact=False,
    )


def _governed_event(runtime: Any, model: Any, event: dict[str, object], state: Any) -> bool:
    name = str(event.get("event") or "")
    if name in {"EXTERNAL_COLLECTION_PHASE_STARTED", "AUDIT_REPROCESS_COLLECTION_PHASE_STARTED"}:
        _set_progress(
            runtime,
            model,
            state,
            phase="EXTERNAL_COLLECTION",
            stage=0.0,
            label="Coleta de integrações e medições",
            detail="aguardando todos os coletores habilitados atingirem estado terminal",
            operation="INTEGRATION:COLLECTION",
        )
        return True
    if name in {"COLLECTOR_STARTED", "COLLECTOR_FINISHED", "COLLECTOR_FAILURE"}:
        collector = str(event.get("collector") or "integração")
        stage = 50.0 if name == "COLLECTOR_STARTED" else 100.0
        _set_progress(
            runtime,
            model,
            state,
            phase="EXTERNAL_COLLECTION",
            stage=stage,
            label="Coleta de integrações e medições",
            detail=f"{collector} · {str(event.get('state') or name).lower()}",
            operation=f"INTEGRATION:{collector}",
        )
        return True
    if name == "EXTERNAL_COLLECTION_PHASE_FINISHED":
        _set_progress(
            runtime,
            model,
            state,
            phase="EXTERNAL_COLLECTION",
            stage=100.0,
            label="Coleta de integrações e medições",
            detail="coletores habilitados encerrados; consolidando evidências",
            operation="LOCAL:COLLECTION_TERMINAL",
        )
        return True
    if name in {"EVIDENCE_SEALED", "AUDIT_REPROCESS_EVIDENCE_SEALED"}:
        _set_progress(
            runtime,
            model,
            state,
            phase="EVIDENCE_SEALING",
            stage=100.0,
            label="Contexto de evidências selado",
            detail=(
                f"versão {event.get('evidence_version') or '-'} · "
                f"snapshot {event.get('evidence_snapshot_id') or '-'}"
            ),
            operation="LOCAL:EVIDENCE_SEALED",
        )
        return True
    if name in {"AI_PHASE_STARTED", "AI_TASK_STARTED", "IMPROVEMENT_INTELLIGENCE_STARTED"}:
        purpose = str(event.get("purpose") or event.get("contract_version") or "análise")
        _set_progress(
            runtime,
            model,
            state,
            phase="AI_ANALYSIS",
            stage=0.0,
            label="Análise por IA sobre evidência selada",
            detail=f"{purpose} · contexto completo já persistido",
            operation=f"AI:{purpose}",
        )
        return True
    if name in {"AI_TASK_FINISHED", "AI_TASK_FAILURE", "IMPROVEMENT_INTELLIGENCE_COMPLETED"}:
        purpose = str(event.get("purpose") or "análise")
        _set_progress(
            runtime,
            model,
            state,
            phase="AI_ANALYSIS",
            stage=100.0,
            label="Análise por IA sobre evidência selada",
            detail=f"{purpose} · {str(event.get('status') or name).lower()}",
            operation=f"AI:{purpose}",
        )
        return True
    if name == "AI_SEALED":
        _set_progress(
            runtime,
            model,
            state,
            phase="FINAL_DERIVATION",
            stage=0.0,
            label="Derivações finais determinísticas",
            detail="IA encerrada; consolidando score, prioridades e recomendações",
            operation="LOCAL:FINAL_DERIVATION",
        )
        return True
    if name == "REPORT_SITE_GENERATED":
        _set_progress(
            runtime,
            model,
            state,
            phase="REPORTING",
            stage=100.0,
            label="Materialização dos relatórios",
            detail="relatório base gerado a partir do estado persistido",
            operation="LOCAL:REPORTING",
        )
        return True
    return False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import console_progress_model as model, console_runtime

    # The base progress model must already be installed so its observer wrapper is the
    # single place reading audit.log. Replace only the policy functions it resolves by
    # global lookup; no second observer/thread is introduced.
    model._ORDER = _CANONICAL_ORDER
    model._CORE_PHASES = _CANONICAL_ORDER

    def workload_weights(state: Any) -> dict[str, float]:
        return _weights(model, state)

    def phase(state: Any, progress: Any | None = None) -> str | None:
        return _canonical_phase(model, state, progress)

    def external_event(runtime: Any, event: dict[str, object], state: Any) -> bool:
        name = str(event.get("event") or "")
        if name.startswith("EXTERNAL_OBSERVABILITY_"):
            stage = 100.0 if name.endswith("FINISHED") or name.endswith("BLOCKED") else 25.0
            service = str(event.get("service") or "observabilidade externa")
            _set_progress(
                runtime,
                model,
                state,
                phase="EXTERNAL_COLLECTION",
                stage=stage,
                label="Coleta de integrações e medições",
                detail=f"{service} · {str(event.get('status') or name).lower()}",
                operation=f"INTEGRATION:{service}",
            )
            return True
        return False

    legacy_pipeline = model._apply_pipeline_event

    def pipeline_event(runtime: Any, event: dict[str, object], state: Any) -> bool:
        if _governed_event(runtime, model, event, state):
            return True
        name = str(event.get("event") or "")
        if name.startswith("AUDIT_PIPELINE_"):
            phase_name = str(event.get("phase") or "").upper()
            mapped = (
                "CORE_COLLECTION"
                if phase_name in {"DISCOVERING", "ACQUIRING"}
                else "DETERMINISTIC_ANALYSIS"
                if phase_name in {"ANALYZING", "COMPARING"}
                else "FINAL_DERIVATION"
                if phase_name in {"SCORING", "RECOMMENDING"}
                else "REPORTING"
                if phase_name == "REPORTING"
                else phase_name
            )
            if mapped in _CANONICAL_ORDER:
                stage = 100.0 if name.endswith("FINISHED") else 0.0
                _set_progress(
                    runtime,
                    model,
                    state,
                    phase=mapped,
                    stage=stage,
                    label={
                        "CORE_COLLECTION": "Coleta e extração core",
                        "DETERMINISTIC_ANALYSIS": "Análise determinística",
                        "FINAL_DERIVATION": "Derivações finais determinísticas",
                        "REPORTING": "Materialização dos relatórios",
                    }.get(mapped, mapped),
                    detail=str(event.get("detail") or event.get("step_key") or mapped),
                    operation=str(event.get("operation") or "LOCAL:PIPELINE"),
                )
                return True
        return legacy_pipeline(runtime, event, state)

    model.workload_weights = workload_weights
    model._phase = phase
    model._apply_external_event = external_event
    model._apply_pipeline_event = pipeline_event

    # Recalculate a currently visible progress object using the canonical ordering.
    original_summary = console_runtime.runtime_progress_summary

    def runtime_progress_summary(state: Any):
        progress = original_summary(state)
        if progress is None or bool(progress.overall_exact):
            return progress
        current_phase = phase(state, progress)
        if current_phase is None or current_phase in model._TERMINAL:
            return progress
        overall = model.projected_overall(state, current_phase, progress.stage_percent)
        return replace(progress, overall_percent=overall, overall_exact=False)

    console_runtime.runtime_progress_summary = runtime_progress_summary
    console_runtime._rasai_governed_progress = True
    _INSTALLED = True


__all__ = ["install"]

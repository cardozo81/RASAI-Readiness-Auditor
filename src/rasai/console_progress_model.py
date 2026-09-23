"""Workload-aware progress model for the interactive console.

Stage percentages remain measured only when a collector/runtime exposes real units.
The overall percentage is a projection of configured/observed workload, not an ETA:
slow repeated browser/provider work receives more weight than fast local bookkeeping.
"""
from __future__ import annotations

from dataclasses import replace
import os
import sqlite3
from typing import Any

_INSTALLED = False
_OBSERVED: dict[int, tuple[int, int]] = {}
_TERMINAL = {"SOURCE_BLOCKED", "COMPLETE", "COMPLETE_WITH_LIMITATIONS", "FAILED", "CANCELLED"}
_CORE_PHASES = (
    "STARTING",
    "INITIALIZING",
    "DISCOVERING",
    "ACQUIRING",
    "ANALYZING",
    "COMPARING",
    "SCORING",
    "RECOMMENDING",
    "REPORTING",
)
_ORDER = (
    *_CORE_PHASES,
    "WEB_PERFORMANCE",
    "SYNTHETIC_UX_APDEX",
    "SYNTHETIC_APDEX",
    "GSC",
    "EXTERNAL_OBSERVABILITY",
    "FINALIZING",
    "SEARCH_INTELLIGENCE",
)

_PHASE_LABELS = {
    "STARTING": "Preparação da execução",
    "INITIALIZING": "Inicialização da auditoria",
    "DISCOVERING": "Descoberta de URLs e recursos",
    "ACQUIRING": "Aquisição HTTP e renderização",
    "ANALYZING": "Extração, regras e análise",
    "COMPARING": "Comparação e integridade de evidências",
    "SCORING": "Cálculo de score e confiabilidade",
    "RECOMMENDING": "Priorização e recomendações",
    "REPORTING": "Gerando relatório",
    "WEB_PERFORMANCE": "Web Performance externo",
    "SYNTHETIC_UX_APDEX": "Synthetic User Experience Apdex",
    "SYNTHETIC_APDEX": "Synthetic Navigation Apdex",
    "GSC": "Google Search Console",
    "EXTERNAL_OBSERVABILITY": "Observabilidade externa",
    "FINALIZING": "Validação e conclusão",
    "SEARCH_INTELLIGENCE": "Search Intelligence / SERP",
    "IMPROVEMENT_INTELLIGENCE": "Análise profunda e melhorias",
}


def _page_count(state: Any) -> int:
    observed = _OBSERVED.get(id(state), (0, 0))[0]
    if observed > 0:
        return observed
    return 1


def _device_count(state: Any) -> int:
    return 2 if str(getattr(state, "device", "mobile")).casefold() == "both" else 1


def _bounded_pages(configured: Any, total: int) -> int:
    try:
        value = int(configured)
    except (TypeError, ValueError):
        value = total
    return total if value == 0 else max(min(value, total), 0)


def _service_ready(service_id: str) -> bool:
    try:
        from rasai.standards_service_registry import service, service_state
        return bool(service_state(service(service_id), os.environ)["effective_enabled"])
    except Exception:
        return False


def _external_operation_count(state: Any) -> int:
    total = 0
    if _service_ready("crux-history"):
        total += 1 + _device_count(state)
    if _service_ready("microsoft-clarity"):
        total += 1
    # Common Crawl is owned by the pre-scoring SARI corroboration path and is
    # deliberately not repeated during post-core observability finalization.
    return total


def _web_performance_enabled(state: Any) -> bool:
    raw = (os.environ.get("RASAI_WEB_PERFORMANCE") or "").strip().casefold()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(getattr(state, "web_performance", False))


def workload_weights(state: Any) -> dict[str, float]:
    """Return relative duration/work units for the configured current execution."""
    pages = max(_page_count(state), 1)
    devices = _device_count(state)
    contexts = max(pages * devices, 1)
    ai_enabled = str(getattr(state, "ai_provider", "none")).casefold() != "none"

    weights: dict[str, float] = {
        "STARTING": 0.8,
        "INITIALIZING": 0.8,
        "DISCOVERING": max(1.2, 0.25 * pages),
        "ACQUIRING": max(5.0, 5.0 * contexts),
        "ANALYZING": max(3.0, 1.2 * contexts) + (5.0 * contexts if ai_enabled else 0.0),
        "COMPARING": 1.8,
        "SCORING": 0.8,
        "RECOMMENDING": 1.5 + (6.0 * pages if bool(getattr(state, "content_remediation", False)) and ai_enabled else 0.0),
        "REPORTING": 2.0,
        "FINALIZING": 1.2,
    }

    if _service_ready("common-crawl"):
        try:
            from rasai.external_observability_policy import common_crawl_max_urls, COMMON_CRAWL_MAX_URLS_ENV
            if common_crawl_max_urls(os.environ.get(COMMON_CRAWL_MAX_URLS_ENV)) > 0:
                weights["SCORING"] += 3.0
        except Exception:
            weights["SCORING"] += 3.0

    if _web_performance_enabled(state):
        web_pages = _bounded_pages(getattr(state, "web_max_pages", pages), pages)
        weights["WEB_PERFORMANCE"] = max(8.0, 14.0 * max(web_pages * devices, 1))

    ux_enabled = bool(getattr(state, "apdex_experience", False))
    nav_enabled = bool(getattr(state, "synthetic_apdex", False))
    if ux_enabled:
        ux_pages = _bounded_pages(getattr(state, "apdex_experience_max_pages", 1), pages)
        samples = max(int(getattr(state, "apdex_experience_samples", 1) or 1), 1)
        weights["SYNTHETIC_UX_APDEX"] = max(4.0, 1.25 * ux_pages * samples)
    if nav_enabled:
        nav_pages = _bounded_pages(getattr(state, "apdex_max_pages", 1), pages)
        samples = max(int(getattr(state, "apdex_samples", 1) or 1), 1)
        shared = ux_enabled and (os.environ.get("RASAI_APDEX_ACQUISITION_MODE") or "auto").strip().casefold() == "auto"
        factor = 0.45 if shared else 1.15
        weights["SYNTHETIC_APDEX"] = max(3.0, factor * nav_pages * devices * samples)

    if _service_ready("google-search-console"):
        weights["GSC"] = 6.0

    external_ops = _external_operation_count(state)
    if external_ops:
        weights["EXTERNAL_OBSERVABILITY"] = max(2.5, 3.0 * external_ops)

    queries = tuple(getattr(state, "search_queries", ()) or ())
    if queries:
        weights["SEARCH_INTELLIGENCE"] = max(4.0, 4.0 * len(queries))

    return weights


def active_stage_plan(state: Any) -> tuple[tuple[str, str], ...]:
    """Return the effective configured stage plan used only for presentation."""
    weights = workload_weights(state)
    return tuple(
        (name, _PHASE_LABELS.get(name, name.replace("_", " ").title()))
        for name in _ORDER
        if name in weights and weights[name] > 0
    )


def phase_bounds(state: Any) -> dict[str, tuple[float, float]]:
    """Normalize active phase work to 0..99; terminal completion alone owns 100."""
    weights = workload_weights(state)
    active = [(name, weights[name]) for name in _ORDER if name in weights and weights[name] > 0]
    total = sum(weight for _, weight in active) or 1.0
    result: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for name, weight in active:
        start = cursor / total * 99.0
        cursor += weight
        end = cursor / total * 99.0
        result[name] = (start, end)
    return result


def _phase(state: Any, progress: Any | None = None) -> str | None:
    status = str(getattr(state, "status", "")).upper()
    operation = str(getattr(state, "operation", "")).upper()
    if status in _TERMINAL:
        return status
    if "GOOGLE_SEARCH_CONSOLE" in operation:
        return "GSC"
    if any(name in operation for name in ("CRUX_HISTORY", "MICROSOFT_CLARITY", "COMMON_CRAWL")) and status == "FINALIZING":
        return "EXTERNAL_OBSERVABILITY"
    if status in _ORDER:
        return status
    label = str(getattr(progress, "label", "")).casefold() if progress is not None else ""
    if "search intelligence" in label or "serp" in label:
        return "SEARCH_INTELLIGENCE"
    if "search console" in label:
        return "GSC"
    if "web performance" in label:
        return "WEB_PERFORMANCE"
    if "user experience" in label:
        return "SYNTHETIC_UX_APDEX"
    if "synthetic apdex" in label:
        return "SYNTHETIC_APDEX"
    return None


def projected_overall(state: Any, phase: str, stage_percent: float | None = None) -> float | None:
    bounds = phase_bounds(state).get(phase)
    if bounds is None:
        return None
    start, end = bounds
    if stage_percent is None:
        return start
    stage = min(max(float(stage_percent), 0.0), 100.0)
    return start + ((end - start) * stage / 100.0)


def _observe_counts(workspace: Any, state: Any) -> None:
    database = getattr(workspace, "database", None)
    if database is None:
        database = getattr(workspace, "root", workspace)
        try:
            database = database / "audit.db"
        except TypeError:
            return
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.15)
        try:
            page_count = int(connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
            snapshot_count = int(connection.execute("SELECT COUNT(*) FROM page_snapshots").fetchone()[0])
        finally:
            connection.close()
    except sqlite3.Error:
        return
    _OBSERVED[id(state)] = (page_count, snapshot_count)


def _apply_pipeline_event(console_runtime: Any, event: dict[str, object], state: Any) -> bool:
    name = str(event.get("event") or "")
    if name not in {
        "AUDIT_PIPELINE_STEP_STARTED",
        "AUDIT_PIPELINE_STEP_FINISHED",
        "AUDIT_PIPELINE_AUX_STARTED",
        "AUDIT_PIPELINE_AUX_FINISHED",
    }:
        return False
    if str(getattr(state, "status", "")).upper() in _TERMINAL:
        return False
    phase = str(event.get("phase") or "").upper()
    if phase not in _CORE_PHASES:
        return False
    if name in {"AUDIT_PIPELINE_AUX_STARTED", "AUDIT_PIPELINE_AUX_FINISHED"}:
        state.status = phase
        state.operation = str(event.get("operation") or "API:AUXILIARY")
        current_progress = console_runtime._RUN_PROGRESS.get(id(state))
        stage = (
            float(current_progress.stage_percent)
            if current_progress is not None and current_progress.stage_percent is not None
            else 0.0
        )
        detail = str(event.get("detail") or "operação auxiliar")
        progress_type = getattr(console_runtime, "_RunProgress")
        console_runtime._RUN_PROGRESS[id(state)] = progress_type(
            label="Cálculo de score e confiabilidade" if phase == "SCORING" else phase,
            percent=stage,
            detail=detail,
            exact=True,
            stage_percent=stage,
            stage_exact=True,
            overall_percent=projected_overall(state, phase, stage),
            overall_exact=False,
        )
        return True
    index = max(int(event.get("step_index") or 1), 1)
    total = max(int(event.get("step_total") or 1), 1)
    step_key = str(event.get("step_key") or "")
    if step_key == "SOURCE_QUALITY_AI_DIAGNOSTIC":
        completed = min(4, total)
    else:
        completed = index if name.endswith("FINISHED") else index - 1
    stage = min(max((completed / total) * 100.0, 0.0), 100.0)
    state.status = phase
    operation = str(event.get("operation") or "LOCAL:PIPELINE")
    current = str(getattr(state, "operation", ""))
    if not (operation.startswith("API_OR_LOCAL:") and current.startswith("API:")):
        state.operation = operation
    detail = str(event.get("detail") or step_key)
    detail_rows: list[tuple[str, str]] = [
        ("Passo da etapa", f"{index} de {total}"),
        ("Subprocesso", detail),
    ]
    if phase == "REPORTING":
        detail_rows.extend((
            ("Fonte", "dados e evidências já persistidos"),
            ("Materialização", "HTML / arquivos em disco"),
            ("Nova coleta da URL", "NÃO"),
        ))
    progress_type = getattr(console_runtime, "_RunProgress")
    console_runtime._RUN_PROGRESS[id(state)] = progress_type(
        label={
            "ANALYZING": "Extração, regras e análise",
            "COMPARING": "Comparação e integridade de evidências",
            "SCORING": "Cálculo de score e confiabilidade",
            "RECOMMENDING": "Priorização e recomendações",
            "REPORTING": "Gerando relatório",
        }.get(phase, phase),
        percent=stage,
        detail=detail,
        exact=True,
        stage_percent=stage,
        stage_exact=True,
        overall_percent=projected_overall(state, phase, stage),
        overall_exact=False,
        detail_rows=tuple(detail_rows),
    )
    return True


def _apply_external_event(console_runtime: Any, event: dict[str, object], state: Any) -> bool:
    name = str(event.get("event") or "")
    allowed = {
        "EXTERNAL_OBSERVABILITY_COLLECTION_STARTED",
        "EXTERNAL_OBSERVABILITY_OPERATION_STARTED",
        "EXTERNAL_OBSERVABILITY_OPERATION_FINISHED",
        "EXTERNAL_OBSERVABILITY_COLLECTION_FINISHED",
        "EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED",
    }
    if name not in allowed:
        return False
    state.status = "FINALIZING"
    progress_type = getattr(console_runtime, "_RunProgress")
    if name == "EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED":
        stage = 100.0
        state.operation = "LOCAL:EXTERNAL_OBSERVABILITY_SKIPPED"
        detail = f"integrações externas não chamadas: {event.get('reason') or 'evidência core incompleta'}"
    elif name == "EXTERNAL_OBSERVABILITY_COLLECTION_STARTED":
        stage = 0.0
        state.operation = "INTEGRATION:EXTERNAL_OBSERVABILITY"
        detail = f"iniciando {int(event.get('operation_total') or 0)} operação(ões) externas pós-core"
    elif name in {"EXTERNAL_OBSERVABILITY_OPERATION_STARTED", "EXTERNAL_OBSERVABILITY_OPERATION_FINISHED"}:
        index = max(int(event.get("operation_index") or 1), 1)
        total = max(int(event.get("operation_total") or 1), 1)
        completed = index if name.endswith("FINISHED") else index - 1
        stage = min(max((completed / total) * 100.0, 0.0), 100.0)
        service = str(event.get("service") or "EXTERNAL")
        state.operation = f"API:{service}"
        status = str(event.get("status") or "em execução")
        detail = f"{service} · operação {index}/{total} · {status}"
    else:
        stage = 100.0
        state.operation = "LOCAL:EXTERNAL_OBSERVABILITY_REPORTS"
        detail = f"observabilidade externa concluída: {event.get('collection_state') or 'UNKNOWN'}; atualizando relatórios"
    external_rows: list[tuple[str, str]] = [("Status", str(event.get("status") or "em execução"))]
    if name in {"EXTERNAL_OBSERVABILITY_OPERATION_STARTED", "EXTERNAL_OBSERVABILITY_OPERATION_FINISHED"}:
        external_rows.extend((
            ("Integração", str(event.get("service") or "EXTERNAL")),
            ("Requisição", f"{max(int(event.get('operation_index') or 1), 1)} de {max(int(event.get('operation_total') or 1), 1)}"),
        ))
    console_runtime._RUN_PROGRESS[id(state)] = progress_type(
        label="Observabilidade externa pós-core",
        percent=stage,
        detail=detail,
        exact=True,
        stage_percent=stage,
        stage_exact=True,
        overall_percent=projected_overall(state, "EXTERNAL_OBSERVABILITY", stage),
        overall_exact=False,
        detail_rows=tuple(external_rows),
    )
    return True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime

    if getattr(console_runtime, "_rasai_workload_progress_model", False):
        _INSTALLED = True
        return

    original_observe = console_runtime.observe_workspace
    original_summary = console_runtime.runtime_progress_summary

    def observe_workspace(workspace: Any, state: Any) -> None:
        original_observe(workspace, state)
        _observe_counts(workspace, state)
        event = console_runtime._last_log_event(workspace)
        if not isinstance(event, dict):
            return
        if _apply_external_event(console_runtime, event, state):
            return
        _apply_pipeline_event(console_runtime, event, state)

    def runtime_progress_summary(state: Any):
        progress = original_summary(state)
        if progress is None:
            return None

        phase = _phase(state, progress)
        if phase is None:
            return progress

        updated = progress
        if not (bool(progress.overall_exact) and progress.overall_percent == 100.0) and phase not in _TERMINAL:
            overall = projected_overall(state, phase, progress.stage_percent)
            if overall is not None:
                updated = replace(progress, overall_percent=overall, overall_exact=False)

        if phase in _TERMINAL:
            return updated

        plan = active_stage_plan(state)
        keys = [name for name, _label in plan]
        if phase not in keys:
            return updated
        position = keys.index(phase)
        previous = plan[position - 1][1] if position > 0 else ""
        following = plan[position + 1][1] if position + 1 < len(plan) else ""
        label = _PHASE_LABELS.get(phase, updated.label)
        return replace(
            updated,
            label=label,
            stage_index=updated.stage_index or position + 1,
            stage_count=updated.stage_count or len(plan),
            stage_count_planned=True,
            previous_label=updated.previous_label or previous,
            next_label=updated.next_label or following,
            current_status=updated.current_status or "EM EXECUÇÃO",
            next_status=updated.next_status or ("AGUARDANDO" if following else ""),
        )

    console_runtime.observe_workspace = observe_workspace
    console_runtime.runtime_progress_summary = runtime_progress_summary
    console_runtime._rasai_workload_progress_model = True
    _INSTALLED = True

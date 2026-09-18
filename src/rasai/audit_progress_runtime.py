"""Operational progress and API-evidence ordering for the canonical audit pipeline.

This runtime is installed only by the public audit entrypoints. It instruments the
already-composed audit runner without changing scoring semantics or adding network
requests. Long operations emit start/finish milestones so the interactive console can
show the operation actually in flight.

Provider-bearing analysis is guarded by persisted/observed upstream evidence: normal
browser rendering must have completed before semantic AI, deterministic extraction
must be complete before semantic analysis, context comparison must precede optional
technical AI, and semantic/context evidence must precede optional content-remediation
AI.
"""
from __future__ import annotations

from functools import wraps
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_FLAGS: dict[str, set[str]] = {}


def _workspace_key(workspace: Any) -> str:
    root = getattr(workspace, "root", workspace)
    try:
        return str(Path(root).resolve())
    except (OSError, TypeError, ValueError):
        return str(root)


def _flags(workspace: Any) -> set[str]:
    return _FLAGS.setdefault(_workspace_key(workspace), set())


def _audit_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    value = kwargs.get("audit_id")
    if value:
        return str(value)
    for item in args:
        if isinstance(item, str) and item.startswith("AUD-"):
            return item
        value = getattr(item, "audit_id", None)
        if value:
            return str(value)
    workspace = kwargs.get("workspace")
    if workspace is None:
        workspace = next((item for item in args if hasattr(item, "root")), None)
    root = getattr(workspace, "root", None)
    if root is not None:
        workspace_name = Path(root).name
        if workspace_name.startswith("AUD-"):
            return workspace_name
    return ""


def _workspace(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any | None:
    value = kwargs.get("workspace")
    if value is not None:
        return value
    for item in args:
        if hasattr(item, "root") and hasattr(item, "database"):
            return item
    return None


def _rendering_completed(workspace: Any) -> bool:
    path = Path(workspace.root) / "logs" / "audit.log"
    if not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(size - 131072, 0))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "RENDERING_COMPLETED":
            return True
    return False


def _semantic_analysis_completed(workspace: Any, audit_id: str) -> bool:
    if not audit_id:
        return False
    try:
        connection = sqlite3.connect(workspace.database)
        try:
            latest = connection.execute(
                """SELECT evidence_snapshot_id FROM ai_evidence_versions
                   WHERE audit_id=? ORDER BY version_number DESC LIMIT 1""",
                (audit_id,),
            ).fetchone()
            if latest is None:
                return False
            row = connection.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN status='COMPLETE' THEN 1 ELSE 0 END)
                   FROM ai_tasks
                   WHERE audit_id=? AND purpose='SEMANTIC_M7' AND evidence_snapshot_id=?""",
                (audit_id, str(latest[0])),
            ).fetchone()
            total = int(row[0] or 0) if row else 0
            complete = int(row[1] or 0) if row else 0
            return total > 0 and complete == total
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def _assert_ready(
    *,
    audit_id: str,
    workspace: Any,
    operation: str,
    required_flags: tuple[str, ...],
) -> None:
    missing = [flag for flag in required_flags if flag not in _flags(workspace)]
    if "RENDERING_COMPLETED" in missing and _rendering_completed(workspace):
        _flags(workspace).add("RENDERING_COMPLETED")
        missing.remove("RENDERING_COMPLETED")
    if "SEMANTIC_ANALYSIS" in missing and _semantic_analysis_completed(workspace, audit_id):
        _flags(workspace).add("SEMANTIC_ANALYSIS")
        missing.remove("SEMANTIC_ANALYSIS")
    if not missing:
        return
    try_append_operational_event(
        workspace,
        "API_EVIDENCE_GATE_BLOCKED",
        level="ERROR",
        audit_id=audit_id,
        operation=operation,
        missing_prerequisites=tuple(missing),
        policy="NO_PROVIDER_CALL_BEFORE_REQUIRED_EVIDENCE",
    )
    raise RuntimeError(
        f"{operation} blocked because required audit evidence is not ready: {', '.join(missing)}"
    )


def _emit(
    workspace: Any,
    event: str,
    *,
    audit_id: str,
    phase: str,
    step_key: str,
    step_index: int,
    step_total: int,
    operation: str,
    detail: str,
    duration_ms: int | None = None,
    status: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "audit_id": audit_id,
        "phase": phase,
        "step_key": step_key,
        "step_index": int(step_index),
        "step_total": int(step_total),
        "operation": operation,
        "detail": detail,
    }
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    if status is not None:
        payload["status"] = status
    try_append_operational_event(workspace, event, **payload)


def _wrap_step(
    fn: Callable[..., Any],
    *,
    phase: str,
    step_key: str,
    step_index: int,
    step_total: int,
    operation: str,
    detail: str,
    completed_flag: str | None = None,
    readiness: Callable[[tuple[Any, ...], dict[str, Any], str, Any], None] | None = None,
) -> Callable[..., Any]:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        workspace = _workspace(args, kwargs)
        audit_id = _audit_id(args, kwargs)
        if workspace is None:
            return fn(*args, **kwargs)
        if readiness is not None:
            readiness(args, kwargs, audit_id, workspace)
        _emit(
            workspace,
            "AUDIT_PIPELINE_STEP_STARTED",
            audit_id=audit_id,
            phase=phase,
            step_key=step_key,
            step_index=step_index,
            step_total=step_total,
            operation=operation,
            detail=detail,
        )
        started = time.monotonic()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            _emit(
                workspace,
                "AUDIT_PIPELINE_STEP_FINISHED",
                audit_id=audit_id,
                phase=phase,
                step_key=step_key,
                step_index=step_index,
                step_total=step_total,
                operation=operation,
                detail=detail,
                duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
                status="ERROR",
            )
            raise
        if completed_flag:
            _flags(workspace).add(completed_flag)
        _emit(
            workspace,
            "AUDIT_PIPELINE_STEP_FINISHED",
            audit_id=audit_id,
            phase=phase,
            step_key=step_key,
            step_index=step_index,
            step_total=step_total,
            operation=operation,
            detail=detail,
            duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
            status="SUCCESS",
        )
        return result

    wrapped._rasai_pipeline_progress = True  # type: ignore[attr-defined]
    return wrapped


def _semantic_ready(_args: tuple[Any, ...], _kwargs: dict[str, Any], audit_id: str, workspace: Any) -> None:
    _assert_ready(
        audit_id=audit_id,
        workspace=workspace,
        operation="SEMANTIC_ANALYSIS",
        required_flags=(
            "RENDERING_COMPLETED",
            "DOM_EXTRACTION",
            "DETERMINISTIC_RULES",
            "JAVASCRIPT_SPA",
            "CONTENT_EXTRACTABILITY",
        ),
    )


def _technical_ai_ready(_args: tuple[Any, ...], kwargs: dict[str, Any], audit_id: str, workspace: Any) -> None:
    if not bool(kwargs.get("technical_ai")):
        return
    _assert_ready(
        audit_id=audit_id,
        workspace=workspace,
        operation="TECHNICAL_AI_ANALYSIS",
        required_flags=("RENDERING_COMPLETED", "CONTEXT_COMPARISON"),
    )


def _content_ai_ready(_args: tuple[Any, ...], kwargs: dict[str, Any], audit_id: str, workspace: Any) -> None:
    if not bool(kwargs.get("enabled")):
        return
    _assert_ready(
        audit_id=audit_id,
        workspace=workspace,
        operation="CONTENT_REMEDIATION_AI",
        required_flags=("SEMANTIC_ANALYSIS", "CONTEXT_COMPARISON"),
    )


def _source_quality_ready(args: tuple[Any, ...], kwargs: dict[str, Any], audit_id: str, workspace: Any) -> None:
    _semantic_ready(args, kwargs, audit_id, workspace)


def wrap_semantic_step(fn: Callable[..., Any]) -> Callable[..., Any]:
    return _wrap_step(
        fn,
        phase="ANALYZING",
        step_key="SEMANTIC_ANALYSIS",
        step_index=5,
        step_total=5,
        operation="API_OR_LOCAL:SEMANTIC_ANALYSIS",
        detail="executando análise semântica somente após renderização, extração e regras locais",
        completed_flag="SEMANTIC_ANALYSIS",
        readiness=_semantic_ready,
    )


def install() -> None:
    """Install progress instrumentation on the final audit-runner call graph."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_runner as runner

    if getattr(runner, "_rasai_pipeline_progress_runtime", False):
        _INSTALLED = True
        return

    runner.execute_m4 = _wrap_step(
        runner.execute_m4,
        phase="ANALYZING",
        step_key="DOM_EXTRACTION",
        step_index=1,
        step_total=5,
        operation="LOCAL:DOM_EXTRACTION",
        detail="extraindo conteúdo, metadados, canonical e dados estruturados de todos os snapshots",
        completed_flag="DOM_EXTRACTION",
    )
    runner.execute_m5 = _wrap_step(
        runner.execute_m5,
        phase="ANALYZING",
        step_key="DETERMINISTIC_RULES",
        step_index=2,
        step_total=5,
        operation="LOCAL:DETERMINISTIC_RULES",
        detail="avaliando regras determinísticas sobre a evidência já coletada",
        completed_flag="DETERMINISTIC_RULES",
    )
    runner.execute_m6 = _wrap_step(
        runner.execute_m6,
        phase="ANALYZING",
        step_key="JAVASCRIPT_SPA",
        step_index=3,
        step_total=5,
        operation="LOCAL:JAVASCRIPT_SPA",
        detail="avaliando comportamento JavaScript/SPA e diferenças de conteúdo renderizado",
        completed_flag="JAVASCRIPT_SPA",
    )
    runner.execute_content_extractability = _wrap_step(
        runner.execute_content_extractability,
        phase="ANALYZING",
        step_key="CONTENT_EXTRACTABILITY",
        step_index=4,
        step_total=5,
        operation="LOCAL:CONTENT_EXTRACTABILITY",
        detail="consolidando conteúdo principal e evidências de extração para todos os contextos",
        completed_flag="CONTENT_EXTRACTABILITY",
    )

    original_source_quality = runner.maybe_explain_source_quality

    @wraps(original_source_quality)
    def source_quality(*args: Any, **kwargs: Any) -> Any:
        workspace = _workspace(args, kwargs)
        audit_id = _audit_id(args, kwargs)
        if workspace is None:
            return original_source_quality(*args, **kwargs)
        _source_quality_ready(args, kwargs, audit_id, workspace)
        _emit(
            workspace,
            "AUDIT_PIPELINE_STEP_STARTED",
            audit_id=audit_id,
            phase="ANALYZING",
            step_key="SOURCE_QUALITY_AI_DIAGNOSTIC",
            step_index=5,
            step_total=5,
            operation="API:SOURCE_QUALITY_AI",
            detail="consultando IA apenas com a evidência de qualidade/origem já coletada",
        )
        started = time.monotonic()
        try:
            result = original_source_quality(*args, **kwargs)
        except Exception:
            _emit(
                workspace,
                "AUDIT_PIPELINE_STEP_FINISHED",
                audit_id=audit_id,
                phase="ANALYZING",
                step_key="SOURCE_QUALITY_AI_DIAGNOSTIC",
                step_index=4,
                step_total=5,
                operation="API:SOURCE_QUALITY_AI",
                detail="diagnóstico auxiliar encerrou com erro; análise principal preservada",
                duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
                status="ERROR",
            )
            raise
        _emit(
            workspace,
            "AUDIT_PIPELINE_STEP_FINISHED",
            audit_id=audit_id,
            phase="ANALYZING",
            step_key="SOURCE_QUALITY_AI_DIAGNOSTIC",
            step_index=4,
            step_total=5,
            operation="API:SOURCE_QUALITY_AI",
            detail="diagnóstico auxiliar encerrado; preparando análise semântica",
            duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
            status="SUCCESS",
        )
        return result

    runner.maybe_explain_source_quality = source_quality

    runner.execute_m7 = wrap_semantic_step(runner.execute_m7)
    runner.execute_m8 = _wrap_step(
        runner.execute_m8,
        phase="COMPARING",
        step_key="CONTEXT_COMPARISON",
        step_index=1,
        step_total=3,
        operation="LOCAL:CONTEXT_COMPARISON",
        detail="comparando evidências entre páginas, dispositivos e contextos",
        completed_flag="CONTEXT_COMPARISON",
    )
    runner.execute_m24 = _wrap_step(
        runner.execute_m24,
        phase="COMPARING",
        step_key="CRAWLING_DISCOVERY_ANALYSIS",
        step_index=2,
        step_total=3,
        operation="LOCAL_OR_API:CRAWLING_DISCOVERY",
        detail="consolidando sinais de crawling/discovery; IA técnica só usa evidência já persistida",
        completed_flag="CRAWLING_DISCOVERY_ANALYSIS",
        readiness=_technical_ai_ready,
    )
    runner.execute_pre_scoring_rules = _wrap_step(
        runner.execute_pre_scoring_rules,
        phase="COMPARING",
        step_key="EVIDENCE_INTEGRITY",
        step_index=3,
        step_total=3,
        operation="LOCAL:EVIDENCE_INTEGRITY",
        detail="validando integridade e consistência das evidências antes do score",
        completed_flag="EVIDENCE_INTEGRITY",
    )
    runner.execute_m9 = _wrap_step(
        runner.execute_m9,
        phase="SCORING",
        step_key="SCORING",
        step_index=1,
        step_total=1,
        operation="LOCAL:SARI_SCORE",
        detail="calculando SARI, Coverage, Confidence e gates com evidência persistida",
        completed_flag="SCORING",
    )
    runner.execute_m10 = _wrap_step(
        runner.execute_m10,
        phase="RECOMMENDING",
        step_key="RECOMMENDATION_BUILD",
        step_index=1,
        step_total=3,
        operation="LOCAL:RECOMMENDATIONS",
        detail="priorizando findings e recomendações acionáveis",
        completed_flag="RECOMMENDATION_BUILD",
    )
    runner.link_findings_to_elements = _wrap_step(
        runner.link_findings_to_elements,
        phase="RECOMMENDING",
        step_key="FINDING_LINKAGE",
        step_index=2,
        step_total=3,
        operation="LOCAL:FINDING_LINKAGE",
        detail="vinculando findings aos elementos/evidências correspondentes",
        completed_flag="FINDING_LINKAGE",
    )
    runner.execute_m20 = _wrap_step(
        runner.execute_m20,
        phase="ANALYZING",
        step_key="CONTENT_REMEDIATION",
        step_index=5,
        step_total=5,
        operation="API_OR_LOCAL:CONTENT_REMEDIATION",
        detail="gerando sugestões de conteúdo somente com findings e evidências semânticas/contextuais já persistidos",
        completed_flag="CONTENT_REMEDIATION",
        readiness=_content_ai_ready,
    )
    runner.execute_m11 = _wrap_step(
        runner.execute_m11,
        phase="REPORTING",
        step_key="REPORT_MODEL",
        step_index=1,
        step_total=4,
        operation="LOCAL:REPORT_MODEL",
        detail="montando o modelo persistido dos relatórios",
        completed_flag="REPORT_MODEL",
    )
    runner.enrich_written_reports = _wrap_step(
        runner.enrich_written_reports,
        phase="REPORTING",
        step_key="REPORT_ENRICHMENT",
        step_index=2,
        step_total=4,
        operation="LOCAL:REPORT_ENRICHMENT",
        detail="enriquecendo relatórios com dados já calculados",
        completed_flag="REPORT_ENRICHMENT",
    )
    runner.materialize_report_site = _wrap_step(
        runner.materialize_report_site,
        phase="REPORTING",
        step_key="HTML_MATERIALIZATION",
        step_index=3,
        step_total=4,
        operation="LOCAL:HTML_MATERIALIZATION",
        detail="materializando o mini-site HTML canônico",
        completed_flag="HTML_MATERIALIZATION",
    )
    runner.enrich_m20_report_site = _wrap_step(
        runner.enrich_m20_report_site,
        phase="REPORTING",
        step_key="FINAL_REPORT_ENRICHMENT",
        step_index=4,
        step_total=4,
        operation="LOCAL:FINAL_REPORT_ENRICHMENT",
        detail="aplicando enriquecimentos finais sem nova aquisição da página",
        completed_flag="FINAL_REPORT_ENRICHMENT",
    )

    try:
        from rasai import external_sari
    except ImportError:
        external_sari = None
    if external_sari is not None and not getattr(external_sari, "_rasai_progress_common_crawl", False):
        original_common_crawl = external_sari.collect_common_crawl_history

        @wraps(original_common_crawl)
        def common_crawl_pre_scoring(*args: Any, **kwargs: Any) -> Any:
            root = kwargs.get("audit_workspace")
            workspace = None
            if root is not None:
                try:
                    from rasai.persistence import AuditWorkspace
                    workspace = AuditWorkspace.open(Path(root))
                except Exception:
                    workspace = None
            if workspace is None:
                return original_common_crawl(*args, **kwargs)
            audit_id = ""
            try:
                import sqlite3
                connection = sqlite3.connect(workspace.database, timeout=0.25)
                try:
                    row = connection.execute("SELECT audit_id FROM audits ORDER BY created_at DESC LIMIT 1").fetchone()
                    audit_id = str(row[0]) if row else ""
                finally:
                    connection.close()
            except Exception:
                pass
            _assert_ready(
                audit_id=audit_id,
                workspace=workspace,
                operation="COMMON_CRAWL_SARI_CORROBORATION",
                required_flags=("RENDERING_COMPLETED", "EVIDENCE_INTEGRITY"),
            )
            try_append_operational_event(
                workspace,
                "AUDIT_PIPELINE_AUX_STARTED",
                audit_id=audit_id,
                phase="SCORING",
                operation="API:COMMON_CRAWL",
                detail="consultando Common Crawl para corroboração positiva bounded antes do cálculo final",
            )
            started = time.monotonic()
            try:
                result = original_common_crawl(*args, **kwargs)
            except Exception:
                try_append_operational_event(
                    workspace,
                    "AUDIT_PIPELINE_AUX_FINISHED",
                    level="WARNING",
                    audit_id=audit_id,
                    phase="SCORING",
                    operation="API:COMMON_CRAWL",
                    detail="Common Crawl indisponível; scoring determinístico continuará sem penalidade externa",
                    status="ERROR",
                    duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
                )
                raise
            try_append_operational_event(
                workspace,
                "AUDIT_PIPELINE_AUX_FINISHED",
                audit_id=audit_id,
                phase="SCORING",
                operation="API:COMMON_CRAWL",
                detail="Common Crawl concluído; retomando cálculo SARI/Coverage/Confidence",
                status="SUCCESS",
                duration_ms=int(max(time.monotonic() - started, 0.0) * 1000.0),
            )
            return result

        external_sari.collect_common_crawl_history = common_crawl_pre_scoring
        external_sari._rasai_progress_common_crawl = True

    runner._rasai_pipeline_progress_runtime = True
    _INSTALLED = True
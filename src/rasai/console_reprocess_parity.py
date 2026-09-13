"""Make selective reprocessing use the standard local execution presentation.

The analytical/recovery engine remains ``audit_reprocess.reprocess_audit``.  This layer
only projects it through the same console frame as a normal audit: header/timing/progress
while running, then persisted usage/cost and artifact actions after completion.
"""
from __future__ import annotations

from contextvars import copy_context
from pathlib import Path
import threading
from types import ModuleType
from typing import Any, Mapping

from rasai.console_audit_workflow import (
    _audit_primary_url,
    _render_reprocess_usage_delta,
    _reprocess_activity,
    _reprocess_live_snapshot,
)

_INSTALLED = False


def _pending_items(state: Any, audit_id: str) -> tuple[Any, ...]:
    try:
        from rasai.audit_fulfillment import list_work_items
        from rasai.persistence import AuditWorkspace

        workspace = AuditWorkspace.open(Path(state.audits_root) / audit_id)
        return tuple(
            item
            for item in list_work_items(workspace, audit_id, pending_only=True)
            if bool(item.required)
        )
    except (OSError, ValueError, RuntimeError):
        return ()


def _reason_text(item: Any) -> str:
    code = str(getattr(item, "last_error_code", "") or "").strip()
    message = str(getattr(item, "last_error_message", "") or "").strip()
    if code and message and message != code:
        return f"{code} - {message}"
    return code or message or "motivo específico não persistido"


def _next_action(item: Any) -> str:
    status = str(getattr(item, "status", "") or "")
    temporal = str(getattr(item, "temporal_mode", "") or "")
    retryable = bool(getattr(item, "retryable", False))
    if status == "WAITING_FOR_DATA":
        return "corrigir/obter o pré-requisito indicado antes de tentar novamente"
    if status in {"BLOCKED", "FAILED_PERMANENT"} or not retryable:
        return "revisar a causa; este requisito não é recuperável por retry automático"
    if temporal == "LIVE_RECOLLECTION" and status != "SUCCESS":
        return "nova tentativa é possível somente enquanto a janela temporal permanecer válida"
    return "o requisito continua retryable; revise o motivo antes de novo reprocessamento"


def render_reprocess_result(result: Any, unresolved: tuple[Any, ...]) -> None:
    """Render RPR-specific facts without replacing the standard usage/actions area."""
    print("\nRESULTADO DO REPROCESSAMENTO")
    print("-" * 100)
    print(f"RPR                  : {result.reprocess_id or '<nenhum; sem trabalho pendente>'}")
    print(f"Processamento        : {result.processing_status}")
    print(f"Score                : {result.score_status}")
    print(f"Relatório            : {result.report_status}")
    print(f"Consolidação elegível: {'SIM' if result.consolidation_eligible else 'NÃO'}")
    print(f"Itens tentados       : {result.attempted_items}")
    print(f"Itens resolvidos     : {result.successful_items}")
    print(f"Sucessos preservados : {result.skipped_success_items}")
    print(f"Itens restantes      : {result.remaining_items}")
    if result.temporal_expired_items:
        print(f"Itens expirados      : {result.temporal_expired_items}")

    if not unresolved:
        return
    print("\nPENDÊNCIAS APÓS O REPROCESSAMENTO")
    print("-" * 100)
    for item in unresolved[:30]:
        print(f"{item.component}/{item.scope_key}")
        print(f"  Status              : {item.status}")
        print(f"  Motivo              : {_reason_text(item)}")
        print(f"  Tentativas          : {item.attempt_count}")
        print(f"  Próxima ação        : {_next_action(item)}")
        valid_until = str(getattr(item, "valid_until", "") or "").strip()
        if valid_until and str(getattr(item, "temporal_mode", "")) == "LIVE_RECOLLECTION":
            print(f"  Janela válida até   : {valid_until}")


def _operation_from_snapshot(snapshot: Mapping[str, Any]) -> str:
    running = snapshot.get("running")
    if not running:
        return "LOCAL:AUD_REPROCESS"
    component = str(running[0])
    if component in {"SEMANTIC_AI", "TECHNICAL_AI", "CONTENT_REMEDIATION_AI"}:
        return "API:AI"
    if component == "WEB_PERFORMANCE":
        return "API:WEB_PERFORMANCE"
    if component == "HTTP_ACQUISITION":
        return "INTEGRATION:HTTP"
    if component == "RENDER_CAPTURE":
        return "LOCAL:BROWSER"
    if component == "CONTENT_EXTRACTION":
        return "LOCAL:EXTRACTION"
    if component in {"SYNTHETIC_APDEX", "EXPERIENCE_APDEX"}:
        return "LOCAL:SYNTHETIC"
    return "LOCAL:AUD_REPROCESS"


def _render_live_frame(console_module: ModuleType, state: Any, audit_root: Path) -> None:
    """Use the same live body as ``run_audit_from_console``."""
    console_module.render_header(state)
    if getattr(state, "audit_id", ""):
        print(f"Audit ID    : {state.audit_id}")
    print(f"Log técnico: {audit_root / 'logs' / 'audit.log'}")


def _run_post_actions(
    console_module: ModuleType,
    state: Any,
    *,
    result: Any,
    unresolved: tuple[Any, ...],
    before_usage: Any | None,
    after_usage: Any | None,
) -> None:
    """Inject RPR facts into the standard post-run cost/actions surface."""
    post_run = getattr(console_module, "_post_run_actions", None)
    normal_usage = getattr(console_module, "_render_actual_usage", None)
    if not callable(post_run) or not callable(normal_usage):
        render_reprocess_result(result, unresolved)
        _render_reprocess_usage_delta(before_usage, after_usage)
        if callable(normal_usage):
            normal_usage(state)
        input("\nENTER para continuar...")
        return

    def reprocess_usage(current_state: Any) -> None:
        render_reprocess_result(result, unresolved)
        _render_reprocess_usage_delta(before_usage, after_usage)
        normal_usage(current_state)

    console_module._render_actual_usage = reprocess_usage
    try:
        requested_exit = bool(post_run(state))
    finally:
        console_module._render_actual_usage = normal_usage
    if requested_exit:
        raise SystemExit(0)


def reprocess_selected(console_module: ModuleType, state: Any, audit_id: str) -> None:
    """Run canonical selective recovery with processing/reprocessing UI parity."""
    from rasai import console_navigation, console_runtime
    from rasai.audit_reprocess import reprocess_audit
    from rasai.console_cost import actual_usage

    pending, successes = console_navigation._work_item_preview(state, audit_id)
    console_module.render_header(state)
    print("REPROCESSAMENTO SELETIVO\n")
    print(f"AUD: {audit_id}")
    if pending or successes:
        print(f"Pendentes/bloqueados : {len(pending)}")
        print(f"Sucessos preservados : {len(successes)}")
        if pending:
            print("\nItens que ainda precisam de resolução:")
            for item in pending[:30]:
                print(f"- {item.component}/{item.scope_key}: {item.status}")
    else:
        print(
            "O estado será reavaliado pelo motor de reprocessamento antes de "
            "qualquer nova tentativa."
        )
    print("\nItens já bem-sucedidos não são repetidos por padrão.")
    print(
        "Chamadas externas/IA só ocorrem quando o requisito correspondente "
        "realmente precisar ser recuperado."
    )
    if input("\nPara iniciar, digite REPROCESSAR: ").strip().upper() != "REPROCESSAR":
        state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
        state.error = "reprocessamento cancelado"
        return

    audit_root = Path(state.audits_root) / audit_id
    before_usage = actual_usage(audit_root)
    baseline_attempts = {
        (str(item.component), str(item.scope_key)): int(item.attempt_count)
        for item in pending
        if bool(getattr(item, "required", True))
    }
    state.audit_id = audit_id
    state.status = "REPROCESSING"
    state.operation = "LOCAL:AUD_REPROCESS"
    state.error = ""
    primary_url = _audit_primary_url(audit_root)
    if primary_url and hasattr(state, "current_url"):
        state.current_url = primary_url

    console_runtime._start_timing(state)
    console_runtime.set_runtime_progress(
        state,
        "Reprocessamento seletivo",
        0.0,
        detail="preparando requisitos pendentes e preservando resultados já válidos",
        exact=False,
    )

    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["result"] = reprocess_audit(
                audit_id,
                audits_root=state.audits_root,
                source="CONSOLE",
            )
        except Exception as exc:  # console boundary: expose engine failures to the operator
            outcome["error"] = exc

    execution_context = copy_context()
    thread = threading.Thread(
        target=lambda: execution_context.run(worker),
        name=f"rasai-reprocess-{audit_id}",
        daemon=True,
    )
    thread.start()

    while thread.is_alive():
        snapshot = _reprocess_live_snapshot(audit_root, audit_id, baseline_attempts)
        total = int(snapshot["total"])
        evaluated = int(snapshot["evaluated"])
        percent = (100.0 * evaluated / total) if total else 0.0
        activity = _reprocess_activity(snapshot)
        state.operation = _operation_from_snapshot(snapshot)
        console_runtime.set_runtime_progress(
            state,
            "Reprocessamento seletivo",
            percent,
            detail=(
                f"{activity}; requisitos avaliados={evaluated}/{total}; "
                f"sucessos anteriores preservados={len(successes)}"
            ),
            exact=False,
        )
        _render_live_frame(console_module, state, audit_root)
        thread.join(timeout=1.0)

    thread.join()
    console_runtime._finish_timing(state)
    after_usage = actual_usage(audit_root)

    error = outcome.get("error")
    if error is not None:
        state.status = "FAILED"
        state.operation = "LOCAL:ERROR"
        state.error = f"{type(error).__name__}: {error}"
        console_runtime.set_runtime_progress(
            state,
            "Falha de reprocessamento",
            100.0,
            detail="reprocessamento interrompido; consulte o motivo e o log técnico",
            exact=True,
        )
        _render_live_frame(console_module, state, audit_root)
        print(f"Relatórios : {audit_root / 'report'}")
        print(f"\nErro        : {state.error}")
        input("\nENTER para continuar...")
        return

    result = outcome["result"]
    unresolved = _pending_items(state, audit_id)
    actual_status = str(result.processing_status)
    state.operation = "LOCAL:DONE"
    state.error = ""

    # ``set_runtime_progress`` recognizes normal execution completion statuses as
    # terminal. Project the RPR completion through that same contract, then restore the
    # authoritative fulfillment status for display. This makes a finished RPR show
    # measured 100% even when the logical AUD remains PARTIAL_RETRYABLE/BLOCKED.
    state.status = "COMPLETE" if actual_status == "COMPLETE" else "COMPLETE_WITH_LIMITATIONS"
    console_runtime.set_runtime_progress(
        state,
        "Reprocessamento concluído",
        100.0,
        detail=(
            f"tentativa concluída; resolvidos={result.successful_items}; "
            f"restantes={result.remaining_items}"
        ),
        exact=True,
    )
    state.status = actual_status

    # Same completion frame emitted by a normal audit before its post-run actions.
    _render_live_frame(console_module, state, audit_root)
    print(f"Relatórios : {audit_root / 'report'}")

    _run_post_actions(
        console_module,
        state,
        result=result,
        unresolved=unresolved,
        before_usage=before_usage,
        after_usage=after_usage,
    )


def install(console_module: ModuleType) -> None:
    """Install after ``console_audit_workflow`` so this is the final RPR presentation."""
    global _INSTALLED
    if _INSTALLED or getattr(console_module, "_rasai_reprocess_parity_installed", False):
        return
    from rasai import console_navigation

    console_navigation._reprocess_selected = reprocess_selected
    console_module._rasai_reprocess_parity_installed = True
    _INSTALLED = True

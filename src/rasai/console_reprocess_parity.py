"""Make selective reprocessing use the standard local execution presentation.

The analytical/recovery engine remains ``audit_reprocess.reprocess_audit``. This layer
only projects it through the same console frame as a normal audit: preparation,
header/timing/progress while running, then persisted usage/cost and artifact actions
after completion.
"""
from __future__ import annotations

from contextvars import ContextVar, copy_context
from pathlib import Path
import json
import sys
import threading
import time
from types import ModuleType
from typing import Any, Mapping

from rasai.console_confirmation_contract import confirm_continue
from rasai.console_ui import (
    GRAY,
    GREEN,
    YELLOW,
    paint,
    semantic_text,
    title_text,
    warning_text,
)
from rasai.console_audit_workflow import (
    _audit_primary_url,
    _render_reprocess_usage_delta,
    _reprocess_activity,
    _reprocess_live_snapshot,
)

_INSTALLED = False
_LIVE_REFRESH_SECONDS = 0.25
_MIN_VISIBLE_PROGRESS_SECONDS = 0.80
_MIN_LIVE_RENDER_SECONDS = 1.00
_LIVE_HEARTBEAT_SECONDS = 5.00


def _live_update_signature(snapshot: Mapping[str, Any], activity: str, operation: str) -> tuple[Any, ...]:
    """Return only operator-visible state used to decide whether a full redraw is useful."""
    return (
        int(snapshot.get("total") or 0),
        int(snapshot.get("evaluated") or 0),
        tuple(snapshot.get("running") or ()),
        str(activity or ""),
        str(operation or ""),
    )


def _should_render_live_update(
    *,
    signature: tuple[Any, ...],
    last_signature: tuple[Any, ...] | None,
    now: float,
    last_rendered_at: float,
) -> bool:
    """Bound full-screen redraws while still keeping long external calls visibly alive."""
    elapsed = max(now - last_rendered_at, 0.0)
    if elapsed >= _LIVE_HEARTBEAT_SECONDS:
        return True
    return signature != last_signature and elapsed >= _MIN_LIVE_RENDER_SECONDS


def _operational_log_offset(audit_root: Path) -> int:
    path = audit_root / "logs" / "audit.log"
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _read_new_improvement_progress(
    audit_root: Path,
    offset: int,
) -> tuple[int, dict[str, Any] | None]:
    """Read only new secret-safe Improvement Intelligence progress events."""
    path = audit_root / "logs" / "audit.log"
    latest: dict[str, Any] | None = None
    try:
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(max(offset, 0))
            for line in stream:
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if str(event.get("event") or "") != "IMPROVEMENT_INTELLIGENCE_STAGE":
                    continue
                latest = event
            new_offset = stream.tell()
    except OSError:
        return offset, None
    return new_offset, latest


def _ai_progress_rows(event: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    stage = str(event.get("stage") or "").strip().upper()
    provider = str(event.get("provider") or "").strip()
    model = str(event.get("model") or "").strip()
    detail = str(event.get("detail") or "").strip()
    percent = event.get("progress_percent")
    try:
        percent_text = f"{float(percent):.0f}% [medido]"
    except (TypeError, ValueError):
        percent_text = "-"
    labels = {
        "EVIDENCE": "Carregando evidências",
        "HTML": "Analisando HTML e semântica",
        "SECURITY": "Avaliando segurança passiva",
        "METRICS": "Correlacionando métricas",
        "DISCOVERY": "Correlacionando descoberta",
        "SEARCH": "Correlacionando Search",
        "AI_ANALYSIS": "Consultando provider de IA",
        "PERSIST": "Persistindo resultado",
        "REPORT_REFRESH": "Atualizando relatório",
    }
    rows: list[tuple[str, str]] = [
        ("Subetapa IA", labels.get(stage, stage.replace("_", " ").title() or "-")),
        ("Andamento interno", percent_text),
    ]
    if provider:
        rows.append(("Provider", provider.upper()))
    if model:
        rows.append(("Modelo", model))
    if detail:
        rows.append(("Executando", detail))
    return tuple(rows)
_ACTIVE_REPROCESS_AUDIT: ContextVar[str] = ContextVar("rasai_active_reprocess_audit", default="")
_RPR_PRESENTATION_CONTEXT: ContextVar[tuple[str, int, tuple[Any, ...]]] = ContextVar(
    "rasai_reprocess_presentation_context",
    default=("", 0, ()),
)
_RPR_COMMAND_CONTEXT: ContextVar[tuple[str, tuple[str, ...], bool] | None] = ContextVar(
    "rasai_reprocess_command_context",
    default=None,
)
_RPR_COMMAND_PLAN: ContextVar[Any | None] = ContextVar("rasai_reprocess_command_plan", default=None)
_RPR_LAST_COMMAND_PLAN: ContextVar[Any | None] = ContextVar("rasai_last_reprocess_command_plan", default=None)


def current_reprocess_command_context() -> tuple[str, tuple[str, ...], bool] | None:
    return _RPR_COMMAND_CONTEXT.get()


def set_reprocess_command_plan(plan: Any | None) -> None:
    _RPR_COMMAND_PLAN.set(plan)


def last_reprocess_command_plan() -> Any | None:
    return _RPR_LAST_COMMAND_PLAN.get()


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
    if status == "NOT_CONFIGURED":
        return "configurar a integração/IA necessária e reprocessar este requisito"
    if status in {"BLOCKED", "FAILED_PERMANENT"} or not retryable:
        return "revisar a causa; este requisito não é recuperável por retry automático"
    if temporal == "LIVE_RECOLLECTION" and status != "SUCCESS":
        return "nova tentativa é possível somente enquanto a janela temporal permanecer válida"
    return "o requisito continua retryable; revise o motivo antes de novo reprocessamento"


def _friendly_status(value: Any) -> str:
    raw = str(value or "").strip()
    labels = {
        "COMPLETE": "Concluída",
        "PARTIAL_RETRYABLE": "Parcial — pode reprocessar",
        "PARTIAL_BLOCKED": "Parcial — há bloqueios",
        "FAILED_FATAL": "Falha definitiva",
        "EXPIRED_FOR_COMPLETION": "Expirada para conclusão",
        "WAITING_FOR_DATA": "Aguardando pré-requisitos",
        "NOT_CONFIGURED": "Não configurada - requer configuração/reprocessamento",
        "REQUESTED_NOT_EXECUTED": "Solicitada - não executada",
        "FAILED_RETRYABLE": "Falha temporária — nova tentativa possível",
        "FAILED_PERMANENT": "Falha definitiva",
        "BLOCKED": "Bloqueado",
        "PENDING": "Pendente",
    }
    return labels.get(raw.upper(), raw.replace("_", " ").strip().capitalize() or "-")


def render_reprocess_preparation(
    console_module: ModuleType,
    state: Any,
    audit_id: str,
    pending: tuple[Any, ...],
    successes: tuple[Any, ...],
) -> None:
    """Render reprocessing as the same preparation/action pattern used by processing."""
    from rasai import console_navigation

    audit_root = Path(state.audits_root) / audit_id
    summary = console_navigation._safe_summary(audit_root, audit_id)

    console_module.render_header(state)
    print(title_text("INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA") + "\n")
    print(title_text("PREPARAR REPROCESSAMENTO"))
    print("-" * 100)
    print(f"AUD                  : {audit_id}")
    print("Situação atual       : " + semantic_text(_friendly_status(summary.get('processing_status')), bold=True))
    if summary:
        print(
            "Requisitos           : "
            f"{summary.get('successful_items', 0)}/{summary.get('required_items', 0)} atendidos"
        )
    print(f"Pendentes/bloqueados : {len(pending)}")
    print(f"Sucessos preservados : {len(successes)}")

    print("\n" + title_text("ESCOPO DESTA TENTATIVA"))
    print("-" * 100)
    if pending:
        for index, item in enumerate(pending, start=1):
            print(
                f"[{index}] {item.component}/{item.scope_key}: "
                f"{semantic_text(_friendly_status(getattr(item, 'status', '')), bold=True)}"
            )
            reason = _reason_text(item)
            if reason != "motivo específico não persistido":
                print(f"    Motivo            : {reason}")
    else:
        print(
            "O estado será reavaliado pelo motor de reprocessamento antes de qualquer "
            "nova tentativa."
        )

    print("\n" + title_text("COMPORTAMENTO"))
    print("-" * 100)
    print("- resultados já bem-sucedidos permanecem preservados e não são repetidos por padrão")
    print("- somente requisitos ainda não satisfeitos e elegíveis são avaliados pelo motor canônico")
    print("- chamadas externas/IA ocorrem apenas quando o requisito realmente precisar ser recuperado")
    print("- consumo adicional desta tentativa e consumo acumulado do AUD aparecem ao final")

    print("\n" + title_text("PRÓXIMA ETAPA"))
    print("Selecione os requisitos da tentativa; depois escolha executar com IA ou sem IA.")


def _select_reprocess_items(state: Any, pending: tuple[Any, ...]) -> tuple[Any, ...] | None:
    if not pending:
        return ()
    from rasai.console_ui import clear_screen

    state.error = ""
    while True:
        clear_screen()
        print(title_text("INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA > SELEÇÃO") + "\n")
        print(title_text("RESUMO DAS ESCOLHAS"))
        print("-" * 100)
        audit_id, preserved, _selected = _RPR_PRESENTATION_CONTEXT.get()
        print(f"AUD                  : {audit_id or '-'}")
        print(f"Pendências disponíveis: {len(pending)}")
        print(f"Sucessos preservados : {preserved}")
        print("\n" + title_text("SELEÇÃO DE ITENS PARA REPROCESSAMENTO"))
        print("-" * 100)
        for index, item in enumerate(pending, 1):
            print(f"{index:>2}. {item.component}/{item.scope_key} · " + semantic_text(_friendly_status(getattr(item, 'status', '')), bold=True))
        print("\nT. Reprocessar todos os itens listados")
        print("   Ou informe números separados por vírgula, por exemplo: 1,3")
        print("V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
            state.error = ""
            return None
        if raw in {"T", "TODOS", "ALL"}:
            state.error = ""
            return pending
        try:
            indexes = {
                int(token.strip())
                for token in raw.split(",")
                if token.strip()
            }
        except ValueError:
            print()
            print("Opção inválida. Use T, V ou números separados por vírgula.")
            print()
            state.error = ""
            continue
        if not indexes or min(indexes) < 1 or max(indexes) > len(pending):
            print()
            print(f"Opção inválida. Informe números entre 1 e {len(pending)}, T ou V.")
            print()
            state.error = ""
            continue
        state.error = ""
        return tuple(item for index, item in enumerate(pending, start=1) if index in indexes)


def _choose_reprocess_ai(state: Any) -> bool | None:
    """Choose the RPR mode; this choice is the final non-destructive authorization."""
    from rasai.console_ui import clear_screen

    state.error = ""
    provider = str(getattr(state, "ai_provider", "none") or "none").strip().casefold()
    model = str(getattr(state, "ai_model", "") or "").strip()
    if provider == "auto":
        current_ai = "AUTO / provider e modelo resolvidos pelo orquestrador"
    elif provider == "none":
        current_ai = "NONE / sem provider configurado para esta tentativa"
    else:
        current_ai = f"{provider.upper()} / {model or '<modelo efetivo/default>'}"

    while True:
        clear_screen()
        audit_id, preserved, selected = _RPR_PRESENTATION_CONTEXT.get()
        print(title_text("INÍCIO > AUDITORIAS / HISTÓRICO > REPROCESSAR AUDITORIA > MODO") + "\n")
        print(title_text("RESUMO DAS ESCOLHAS"))
        print("-" * 100)
        print(f"AUD                  : {audit_id or '-'}")
        print(f"Itens selecionados   : {len(selected)}")
        if selected:
            print("Reprocessar           : " + ", ".join(f"{item.component}/{item.scope_key}" for item in selected))
        print(f"Sucessos preservados : {preserved}")
        print(f"Configuração de IA   : {current_ai}")
        ai_selected = sum(
            1
            for item in selected
            if str(getattr(item, "component", "") or "").upper()
            in {"IMPROVEMENT_INTELLIGENCE", "SEMANTIC_AI", "TECHNICAL_AI", "CONTENT_REMEDIATION_AI"}
        )
        print(f"Itens selecionados com IA: {ai_selected}")
        if ai_selected == 0:
            print(
                "INFO                 : "
                + warning_text(
                    "IA não se aplica ao escopo selecionado; pendências não selecionadas "
                    "não serão incluídas nesta tentativa."
                )
            )

        # Recalculate the forecast for exactly the selected scope. This is read-only and
        # does not start the RPR or call a provider.
        if audit_id and selected:
            try:
                from rasai.console_reprocess_final_refinements import _render_reprocess_cost_preview

                _render_reprocess_cost_preview(state, audit_id, selected)
            except Exception:
                pass

        print("\n" + title_text("COMO EXECUTAR O REPROCESSAMENTO"))
        print("-" * 100)
        if ai_selected:
            print("1. Reprocessar itens selecionados com IA quando aplicável")
        else:
            print("1. Reprocessar itens selecionados com IA quando aplicável [sem efeito neste escopo]")
        print("2. Reprocessar itens selecionados sem IA")
        print("V. Voltar")
        raw = input("Escolha: ").strip().casefold()
        if raw in {"2", "", "n", "nao", "não", "no", "0", "false", "off"}:
            state.error = ""
            return False
        if raw in {"1", "s", "sim", "y", "yes", "true", "on"}:
            state.error = ""
            return True
        if raw in {"v", "voltar"}:
            state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
            state.error = ""
            return None
        print("\nOpção inválida. Use 1, 2 ou V.")
        state.error = ""


def _confirm_reprocess(state: Any) -> bool:
    confirmed = confirm_continue(
        "Confirmar e iniciar reprocessamento",
        back_label="Voltar sem reprocessar",
        show_options=False,
    )
    if confirmed:
        return True
    state.operation = "LOCAL:AUD_REPROCESS_CANCELLED"
    state.error = ""
    return False


def render_reprocess_result(result: Any, unresolved: tuple[Any, ...]) -> None:
    """Render RPR-specific facts without replacing the standard usage/actions area."""
    print("\n" + title_text("RESULTADO DO REPROCESSAMENTO"))
    print("-" * 100)
    print(f"RPR                  : {result.reprocess_id or '<nenhum; sem trabalho pendente>'}")
    print("Execução do RPR      : " + paint("CONCLUÍDA", GREEN, bold=True))
    print("Estado diagnóstico   : " + semantic_text(result.processing_status, bold=True))
    print("Score                : " + semantic_text(result.score_status))
    print("Relatório            : " + semantic_text(result.report_status))
    print(
        "Consolidação elegível: "
        + (paint("SIM", GREEN, bold=True) if result.consolidation_eligible else paint("NÃO", YELLOW, bold=True))
    )
    if hasattr(result, "selected_items"):
        print(f"Selecionados         : {result.selected_items}")
        print(f"Não selecionados     : {result.unselected_items}")
    print(f"Itens tentados       : {result.attempted_items}")
    print(f"Itens resolvidos     : {result.successful_items}")
    print(f"Sucessos preservados : {result.skipped_success_items}")
    print(f"Itens restantes AUD  : {result.remaining_items}")
    if result.temporal_expired_items:
        print(f"Itens expirados      : {result.temporal_expired_items}")

    if not unresolved:
        return
    print("\n" + warning_text("PENDÊNCIAS APÓS O REPROCESSAMENTO", bold=True))
    print("-" * 100)
    _audit_id, _preserved, selected = _RPR_PRESENTATION_CONTEXT.get()
    selected_keys = {
        (str(getattr(entry, "component", "")), str(getattr(entry, "scope_key", "")))
        for entry in selected
    }
    for item in unresolved:
        current_key = (str(item.component), str(item.scope_key))
        selected_now = current_key in selected_keys
        print(f"{item.component}/{item.scope_key}")
        print(
            "  Nesta tentativa     : "
            + (
                paint("SELECIONADO", GREEN, bold=True)
                if selected_now
                else paint("NÃO SELECIONADO", YELLOW, bold=True)
            )
        )
        print("  Status              : " + semantic_text(item.status, bold=True))
        reason_label = "Motivo" if selected_now else "Motivo persistido"
        print(f"  {reason_label:<20}: {_reason_text(item)}")
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
    sys.stdout.flush()


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
    if _ACTIVE_REPROCESS_AUDIT.get() == audit_id:
        # Defensive guard against accidental recursive composition of console wrappers.
        return
    active_token = _ACTIVE_REPROCESS_AUDIT.set(audit_id)
    try:
        _reprocess_selected_once(console_module, state, audit_id)
    finally:
        _ACTIVE_REPROCESS_AUDIT.reset(active_token)


def _reprocess_selected_once(console_module: ModuleType, state: Any, audit_id: str) -> None:
    from rasai import console_navigation, console_runtime
    from rasai.audit_reprocess import reprocess_audit
    from rasai.console_cost import actual_usage

    # A previous screen may leave a human-facing error in state.error. It must not leak
    # into a fresh RPR preparation or appear beside the next input prompt.
    state.error = ""
    pending, successes = console_navigation._work_item_preview(state, audit_id)
    _RPR_PRESENTATION_CONTEXT.set((audit_id, len(successes), ()))
    render_reprocess_preparation(console_module, state, audit_id, pending, successes)
    selected = _select_reprocess_items(state, pending)
    if selected is None:
        return
    if not selected:
        state.error = "não há requisito pendente selecionável para reprocessamento"
        return
    _RPR_PRESENTATION_CONTEXT.set((audit_id, len(successes), tuple(selected)))
    use_ai = _choose_reprocess_ai(state)
    if use_ai is None:
        return

    from rasai.reprocess_policy import item_key

    selected_keys = tuple(item_key(item.component, item.scope_key) for item in selected)

    # The mode choice above is the execution authorization. Do not stack another
    # confirmation screen for the same non-destructive intent.
    _RPR_COMMAND_CONTEXT.set((audit_id, selected_keys, bool(use_ai)))
    try:
        if not _confirm_reprocess(state):
            return
    finally:
        _RPR_COMMAND_CONTEXT.set(None)

    pending = selected
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
        "Executando requisitos selecionados",
        0.0,
        detail="iniciando a tentativa sobre o escopo selecionado",
        exact=False,
        stage_index=1,
        stage_count=3,
        previous_label="Preparando reprocessamento",
        next_label="Gerando relatório",
        detail_rows=(
            ("Status", "Iniciando reprocessamento"),
            ("Selecionados", str(len(pending))),
            ("Avaliados neste RPR", f"0 de {len(pending)}"),
            ("Sucessos preservados", str(len(successes))),
        ),
    )

    # Render before the worker starts. This guarantees visible feedback even when the
    # selected recovery finishes before the first polling cycle (common for local APDEX).
    visible_since = time.monotonic()
    _render_live_frame(console_module, state, audit_root)

    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            from rasai.reprocess_policy import reprocess_policy

            with reprocess_policy(
                selected_items=selected_keys,
                use_ai=use_ai,
                ai_provider=(str(getattr(state, "ai_provider", "none") or "none") if use_ai else None),
                ai_model=(str(getattr(state, "ai_model", "") or "") if use_ai else None),
                ai_reasoning=(str(getattr(state, "ai_reasoning", "") or "") if use_ai else None),
            ):
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
    log_offset = _operational_log_offset(audit_root)
    latest_ai_progress: dict[str, Any] | None = None
    thread.start()

    last_rendered_at = visible_since
    last_signature: tuple[Any, ...] | None = None
    while thread.is_alive():
        # Poll frequently enough to notice completion quickly, but do not clear/redraw
        # the whole Windows terminal on every poll. Full redraws are capped at 1 Hz for
        # state changes, with a low-frequency heartbeat for long external calls.
        thread.join(timeout=_LIVE_REFRESH_SECONDS)
        if not thread.is_alive():
            break

        snapshot = _reprocess_live_snapshot(audit_root, audit_id, baseline_attempts)
        total = int(snapshot["total"])
        evaluated = int(snapshot["evaluated"])
        work_item_percent = (100.0 * evaluated / total) if total else 0.0
        activity = _reprocess_activity(snapshot)
        state.operation = _operation_from_snapshot(snapshot)

        log_offset, new_ai_progress = _read_new_improvement_progress(audit_root, log_offset)
        if new_ai_progress is not None:
            latest_ai_progress = new_ai_progress

        internal_percent: float | None = None
        ai_rows: tuple[tuple[str, str], ...] = ()
        if latest_ai_progress is not None:
            try:
                internal_percent = min(
                    max(float(latest_ai_progress.get("progress_percent")), 0.0),
                    100.0,
                )
            except (TypeError, ValueError):
                internal_percent = None
            ai_rows = _ai_progress_rows(latest_ai_progress)
            ai_detail = str(latest_ai_progress.get("detail") or "").strip()
            if ai_detail:
                activity = ai_detail
            ai_stage = str(latest_ai_progress.get("stage") or "").strip().upper()
            provider = str(latest_ai_progress.get("provider") or "").strip()
            if ai_stage == "AI_ANALYSIS":
                state.operation = f"API:{provider.upper() or 'AI'}"
            elif ai_stage:
                state.operation = f"LOCAL:IMPROVEMENT_{ai_stage}"

        work_items_done = bool(total and evaluated >= total)
        if work_items_done:
            # Once every selected work item is evaluated, the worker is in local
            # reconciliation/report materialization. Do not keep reporting stage 1 as
            # 100% while a later stage is visibly pending.
            console_runtime.set_runtime_progress(
                state,
                "Gerando relatório",
                0.0,
                detail="requisitos encerrados; consolidando dados persistidos e materializando o relatório",
                exact=False,
                stage_index=2,
                stage_count=3,
                previous_label="Executando requisitos selecionados",
                next_label="Validação e conclusão",
                detail_rows=(
                    ("Status", "Materializando resultados"),
                    ("Selecionados", str(total)),
                    ("Avaliados neste RPR", f"{evaluated} de {total}"),
                    ("Sucessos preservados", str(len(successes))),
                    ("Subprocesso", "consolidação / persistência / HTML / artefatos"),
                ),
                overall_percent_override=100.0 / 3.0,
                overall_exact_override=False,
            )
            activity = "consolidando dados persistidos e materializando o relatório"
        else:
            stage_percent = internal_percent
            stage_exact = internal_percent is not None
            overall_basis = internal_percent if internal_percent is not None else work_item_percent
            console_runtime.set_runtime_progress(
                state,
                "Executando requisitos selecionados",
                work_item_percent,
                detail=activity,
                exact=False,
                stage_index=1,
                stage_count=3,
                previous_label="Preparando reprocessamento",
                next_label="Gerando relatório",
                detail_rows=(
                    ("Status", "Reprocessando"),
                    ("Selecionados", str(total)),
                    ("Avaliados neste RPR", f"{evaluated} de {total}"),
                    ("Sucessos preservados", str(len(successes))),
                    ("Requisito atual", _reprocess_activity(snapshot)),
                    *ai_rows,
                ),
                stage_percent_override=stage_percent,
                stage_exact_override=stage_exact,
                overall_percent_override=(overall_basis / 3.0),
                overall_exact_override=False,
            )
        now = time.monotonic()
        signature = (
            *_live_update_signature(snapshot, activity, state.operation),
            None if internal_percent is None else round(internal_percent, 3),
        )
        if _should_render_live_update(
            signature=signature,
            last_signature=last_signature,
            now=now,
            last_rendered_at=last_rendered_at,
        ):
            _render_live_frame(console_module, state, audit_root)
            last_rendered_at = now
            last_signature = signature

    thread.join()

    # The engine may finish in milliseconds. Keep a truthful completion transition on
    # screen long enough to be perceived by a human operator instead of jumping directly
    # from C to the result screen and looking frozen.
    console_runtime.set_runtime_progress(
        state,
        "Gerando relatório",
        100.0,
        detail="requisitos encerrados; consolidação, persistência e materialização do relatório concluídas",
        exact=True,
        stage_index=2,
        stage_count=3,
        previous_label="Executando requisitos selecionados",
        next_label="Validação e conclusão",
        detail_rows=(
            ("Status", "Materialização concluída"),
            ("Sucessos preservados", str(len(successes))),
            ("Subprocesso", "consolidação / persistência / HTML / artefatos"),
        ),
        stage_percent_override=100.0,
        stage_exact_override=True,
        overall_percent_override=(200.0 / 3.0),
        overall_exact_override=False,
    )
    state.operation = "LOCAL:AUD_REPROCESS"
    _render_live_frame(console_module, state, audit_root)
    elapsed_visible = time.monotonic() - visible_since
    if elapsed_visible < _MIN_VISIBLE_PROGRESS_SECONDS:
        time.sleep(_MIN_VISIBLE_PROGRESS_SECONDS - elapsed_visible)

    console_runtime._finish_timing(state)
    after_usage = actual_usage(audit_root)

    command_plan = _RPR_COMMAND_PLAN.get()
    if command_plan is not None:
        try:
            from rasai.execution_commands import executed, record

            command_plan = executed(command_plan)
            _RPR_LAST_COMMAND_PLAN.set(command_plan)
            record(command_plan, state.audits_root, audit_id, append=True)
        except Exception:
            # Command logging is observability only and cannot alter the RPR result.
            pass
        finally:
            _RPR_COMMAND_PLAN.set(None)

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
        print(f"Relatórios : {audit_root / 'report-catalog'}")
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
        "Validação e conclusão",
        100.0,
        detail="reprocessamento concluído e resultado final materializado",
        exact=True,
        stage_index=3,
        stage_count=3,
        stage_count_planned=False,
        previous_label="Gerando relatório",
        next_label="",
        current_status="CONCLUÍDA",
        detail_rows=(
            ("RPR", str(result.reprocess_id or "-")),
            ("Resolvidos neste RPR", str(result.successful_items)),
            ("Sucessos preservados", str(result.skipped_success_items)),
            ("Itens restantes", str(result.remaining_items)),
        ),
    )
    state.status = actual_status

    # Same completion frame emitted by a normal audit before its post-run actions.
    _render_live_frame(console_module, state, audit_root)
    print(f"Relatórios : {audit_root / 'report-catalog'}")

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
